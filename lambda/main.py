"""
Puppy Adoption Notifier Lambda Function

This Lambda function fetches data about adoptable dogs from the Williamson County Pet Shelter,
filters for puppies under 6 months old, and sends an email report with their details.
"""

import os
import re
import logging
from typing import List, Dict, Optional, Any

import boto3
import requests
from bs4 import BeautifulSoup, Tag

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Constants
BASE_URL = "https://ws.petango.com/webservices/adoptablesearch/"
SHELTER_URL = f"{BASE_URL}wsAdoptableAnimals2.aspx?species=Dog&sex=A&agegroup=All&location=&site=&onhold=A&orderby=ID&colnum=4&authkey=htr0d8cmdxn6kjq4i3brxlvgmx8e610khmut6wkjxayue3rdff&recAmount=&detailsInPopup=Yes&featuredPet=Include&stageID="
EMAIL_SUBJECT = "Daily Adoptable Puppies Report"
MAX_AGE_MONTHS = 6  # Maximum age in months to be considered a puppy

# AWS clients
ses_client = boto3.client("ses", region_name=os.environ.get("AWS_REGION", "us-east-1"))


class PuppyNotFoundError(Exception):
    """Exception raised when no puppies are found in the shelter."""

    pass


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Main Lambda handler function.

    Args:
        event: Lambda event data
        context: Lambda context object

    Returns:
        Dict containing status code and response message
    """
    logger.info("Lambda function started")
    logger.info(f"Event: {event}")

    try:
        # Get environment variables
        email_from = os.environ.get("EMAIL_FROM")
        email_to = os.environ.get("EMAIL_TO")

        if not email_from or not email_to:
            raise ValueError(
                "Email configuration missing. Check environment variables."
            )

        # Main processing flow
        puppies = fetch_and_filter_puppies()
        send_email_report(email_from, email_to, puppies)

        logger.info("Lambda function completed successfully")
        return {"statusCode": 200, "body": "Email sent successfully!"}

    except PuppyNotFoundError:
        logger.info("No puppies found, sent empty report")
        return {"statusCode": 200, "body": "No puppies found"}
    except ValueError as e:
        logger.error(f"Configuration error: {str(e)}")
        return {"statusCode": 400, "body": str(e)}
    except Exception as e:
        logger.error(f"Error in lambda_handler: {str(e)}", exc_info=True)
        return {"statusCode": 500, "body": str(e)}


def age_to_months(age_text: str) -> int:
    """
    Convert age text (e.g. "2 years 3 months") to total months.

    Args:
        age_text: String representation of age

    Returns:
        Total age in months
    """
    years = months = 0
    year_match = re.search(r"(\d+)\s*year", age_text)
    month_match = re.search(r"(\d+)\s*month", age_text)

    if year_match:
        years = int(year_match.group(1))
    if month_match:
        months = int(month_match.group(1))

    return (years * 12) + months


def extract_detail_url(js_href: str) -> Optional[str]:
    """
    Extract the actual URL from a JavaScript function call.

    Args:
        js_href: JavaScript href attribute containing a function call

    Returns:
        Extracted URL or None if unable to parse
    """
    url_match = re.search(r"poptastic\('([^']+)'\)", js_href)
    if not url_match:
        return None

    relative_url = url_match.group(1)
    return f"{BASE_URL}{relative_url}"


def fetch_dog_details(detail_url: str, dog_name: str) -> Optional[Dict[str, Any]]:
    """
    Fetch and parse a dog's detailed information.

    Args:
        detail_url: URL to the dog's detail page
        dog_name: Name of the dog for logging purposes

    Returns:
        Dictionary with dog details and HTML content, or None if fetch fails
    """
    logger.info(f"Fetching details for dog {dog_name} from {detail_url}")

    try:
        response = requests.get(detail_url, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        layout_div = soup.find(id="DefaultLayoutDiv")

        if not layout_div:
            logger.warning(f"DefaultLayoutDiv not found for dog {dog_name}")
            return None

        # Fix relative image URLs
        fix_relative_image_urls(layout_div, BASE_URL)

        # Extract main image URLs
        image_urls = extract_image_urls(soup)

        # Get basic details
        dog_details = {
            "name": get_text_by_id(soup, "lbName") or dog_name,
            "id": get_text_by_id(soup, "lblID") or "Unknown",
            "breed": get_text_by_id(soup, "lbBreed") or "Unknown",
            "age": get_text_by_id(soup, "lbAge") or "Unknown",
            "gender": get_text_by_id(soup, "lbSex") or "Unknown",
            "size": get_text_by_id(soup, "lblSize") or "Unknown",
            "color": get_text_by_id(soup, "lblColor") or "Unknown",
            "detail_url": detail_url,
            "image_urls": image_urls,
            "layout_html": str(layout_div),
        }

        return dog_details

    except requests.RequestException as e:
        logger.error(f"Error fetching details for {dog_name}: {str(e)}")
        return None


def get_text_by_id(soup: BeautifulSoup, element_id: str) -> Optional[str]:
    """
    Helper function to extract text from an element by ID.

    Args:
        soup: BeautifulSoup object
        element_id: ID of the element to find

    Returns:
        Text content or None if element not found
    """
    element = soup.find(id=element_id)
    return element.get_text(strip=True) if element else None


def fix_relative_image_urls(layout_div: Tag, base_url: str) -> None:
    """
    Fix relative image URLs in the HTML content.

    Args:
        layout_div: BeautifulSoup Tag containing the layout
        base_url: Base URL to prepend to relative paths
    """
    for img in layout_div.find_all("img"):
        if not img.get("src"):
            continue

        src = img["src"]
        if src.startswith("../"):
            img["src"] = f"https://ws.petango.com/{src.replace('../', '')}"
        elif src.startswith("images/"):
            img["src"] = f"{base_url}{src}"


def extract_image_urls(soup: BeautifulSoup) -> List[str]:
    """
    Extract all image URLs from a dog's detail page.

    Args:
        soup: BeautifulSoup object of the detail page

    Returns:
        List of image URLs
    """
    image_urls = []

    # Get main image
    main_img = soup.find(id="imgAnimalPhoto")
    if main_img and main_img.get("src"):
        image_urls.append(main_img["src"])

    # Get additional images from onclick handlers
    photo_links = soup.find_all("a", onclick=re.compile(r"loadPhoto\('([^']+)'\)"))
    for link in photo_links:
        match = re.search(r"loadPhoto\('([^']+)'\)", link["onclick"])
        if match:
            img_url = match.group(1)
            if img_url not in image_urls:
                image_urls.append(img_url)

    return image_urls


def fetch_and_filter_puppies() -> List[Dict[str, Any]]:
    """
    Fetch all dogs from the shelter and filter for puppies under MAX_AGE_MONTHS.

    Returns:
        List of dictionaries containing puppy details

    Raises:
        Exception: If unable to fetch the shelter data
    """
    logger.info(f"Fetching data from URL: {SHELTER_URL}")

    response = requests.get(SHELTER_URL, timeout=10)
    if response.status_code != 200:
        logger.error(f"Failed to fetch data: {response.status_code}")
        raise Exception(f"Failed to fetch data: {response.status_code}")

    logger.info(f"Data fetched successfully. Response size: {len(response.text)} bytes")

    soup = BeautifulSoup(response.text, "html.parser")
    dogs = soup.find_all("li")
    logger.info(f"Found {len(dogs)} total dogs on the page")

    filtered_puppies = []

    for dog in dogs:
        age_element = dog.find(class_="list-animal-age")
        name_element = dog.find(class_="list-animal-name")

        if not age_element or not name_element:
            continue

        age_text = age_element.get_text(strip=True)
        name = name_element.get_text(strip=True)
        total_months = age_to_months(age_text)

        logger.info(f"Processing dog: {name}, Age: {age_text} ({total_months} months)")

        # Skip if not a puppy
        if total_months >= MAX_AGE_MONTHS:
            continue

        # Get link to details page
        link_element = dog.find("a")
        if not link_element or not link_element.get("href"):
            logger.warning(f"No link found for dog {name}")
            continue

        detail_url = extract_detail_url(link_element["href"])
        if not detail_url:
            logger.warning(
                f"Could not parse detail URL from JavaScript link for dog {name}"
            )
            continue

        # Fetch detailed information
        dog_details = fetch_dog_details(detail_url, name)
        if dog_details:
            filtered_puppies.append(dog_details)

    logger.info(
        f"Filtered to {len(filtered_puppies)} puppies (< {MAX_AGE_MONTHS} months old)"
    )
    return filtered_puppies


def format_puppy_html(puppy: Dict[str, Any]) -> str:
    """
    Format a puppy's information into HTML for the email.

    Args:
        puppy: Dictionary containing puppy details

    Returns:
        HTML string for the puppy
    """
    html = f"""
    <div style='margin-bottom:30px; border-bottom:1px solid #ccc; padding-bottom:20px;'>
        <h2>{puppy["name"]}</h2>
        <table style='width:100%; border-collapse: collapse;'>
            <tr><td style='font-weight:bold;width:150px;'>ID:</td><td>{puppy["id"]}</td></tr>
            <tr><td style='font-weight:bold;'>Breed:</td><td>{puppy["breed"]}</td></tr>
            <tr><td style='font-weight:bold;'>Age:</td><td>{puppy["age"]}</td></tr>
            <tr><td style='font-weight:bold;'>Gender:</td><td>{puppy["gender"]}</td></tr>
            <tr><td style='font-weight:bold;'>Size:</td><td>{puppy["size"]}</td></tr>
            <tr><td style='font-weight:bold;'>Color:</td><td>{puppy["color"]}</td></tr>
        </table>
        <div style='margin-top:15px;'>
    """

    # Add all images
    for img_url in puppy["image_urls"]:
        html += f"<img src='{img_url}' style='max-width:100%; margin:5px 0;' /><br>"

    html += f"""
        </div>
        <div style='margin-top:10px;'>
            <a href='{puppy["detail_url"]}' style='background-color:#4CAF50; color:white; padding:10px 15px; text-decoration:none; display:inline-block; border-radius:4px;'>View Details</a>
        </div>
    </div>
    """

    return html


def send_email_report(
    email_from: str, email_to: str, puppies: List[Dict[str, Any]]
) -> None:
    """
    Send an email report with the puppies information.

    Args:
        email_from: Sender email address
        email_to: Recipient email address(es)
        puppies: List of puppy details to include in the report

    Raises:
        Exception: If email sending fails
    """
    logger.info(f"Preparing email from: {email_from} to: {email_to}")

    # Parse recipients
    email_recipients = email_to.split(",") if isinstance(email_to, str) else email_to

    # Prepare email body
    if not puppies:
        body = "<p>No puppies under 6 months found today.</p>"
        logger.info("No puppies found to report")
    else:
        puppy_html_sections = [format_puppy_html(puppy) for puppy in puppies]

        body = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                h1 {{ color: #333366; }}
                h2 {{ color: #4CAF50; }}
                table {{ margin-bottom: 15px; }}
                td {{ padding: 5px; }}
            </style>
        </head>
        <body>
            <h1>Adoptable Puppies (< {MAX_AGE_MONTHS} Months) - {len(puppies)} Found</h1>
            {"".join(puppy_html_sections)}
        </body>
        </html>
        """
        logger.info(
            f"Sending email with {len(puppies)} puppies to {len(email_recipients)} recipients"
        )

    # Send email
    try:
        logger.info("Sending email through SES")
        response = ses_client.send_email(
            Source=email_from,
            Destination={"ToAddresses": email_recipients},
            Message={
                "Subject": {"Data": EMAIL_SUBJECT},
                "Body": {"Html": {"Data": body}},
            },
        )
        logger.info(f"Email sent successfully. Message ID: {response.get('MessageId')}")
    except Exception as e:
        logger.error(f"Failed to send email: {str(e)}")
        raise
