import requests
import boto3
import re
import os
import logging
from bs4 import BeautifulSoup

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# AWS SES Config
SES_CLIENT = boto3.client(
    "ses", region_name=os.environ.get("AWS_REGION", "us-east-1")
)  # Get region from environment variable or default to us-east-1
EMAIL_FROM = os.environ.get("EMAIL_FROM")  # Get from environment variable
EMAIL_TO = os.environ.get("EMAIL_TO")  # Get from environment variable
SUBJECT = "Daily Adoptable Puppies Report"

# Williamson County, TX Pet Shelter URL
URL = "https://ws.petango.com/webservices/adoptablesearch/wsAdoptableAnimals2.aspx?species=Dog&sex=A&agegroup=All&location=&site=&onhold=A&orderby=ID&colnum=4&authkey=htr0d8cmdxn6kjq4i3brxlvgmx8e610khmut6wkjxayue3rdff&recAmount=&detailsInPopup=Yes&featuredPet=Include&stageID="


def fetch_and_filter_dogs():
    logger.info(f"Fetching data from URL: {URL}")
    response = requests.get(URL)
    if response.status_code != 200:
        logger.error(f"Failed to fetch data: {response.status_code}")
        raise Exception(f"Failed to fetch data: {response.status_code}")

    logger.info(f"Data fetched successfully. Response size: {len(response.text)} bytes")
    soup = BeautifulSoup(response.text, "html.parser")

    dogs = soup.find_all("li")  # Find all list items
    logger.info(f"Found {len(dogs)} total dogs on the page")
    filtered_dogs = []

    def age_to_months(age_text):
        years = months = 0
        year_match = re.search(r"(\d+)\s*year", age_text)
        month_match = re.search(r"(\d+)\s*month", age_text)
        if year_match:
            years = int(year_match.group(1))
        if month_match:
            months = int(month_match.group(1))
        return (years * 12) + months

    for dog in dogs:
        age_element = dog.find(class_="list-animal-age")
        if age_element:
            age_text = age_element.get_text(strip=True)
            total_months = age_to_months(age_text)
            name_element = dog.find(class_="list-animal-name")

            if name_element:
                name = name_element.get_text(strip=True)
                logger.info(
                    f"Processing dog: {name}, Age: {age_text} ({total_months} months)"
                )

                if total_months < 6:  # Changed to filter puppies < 6 months old
                    link_element = dog.find("a")

                    if link_element:
                        # Extract the real URL from the JavaScript link
                        js_href = link_element["href"]
                        # Use regex to extract the URL inside the poptastic function
                        url_match = re.search(r"poptastic\('([^']+)'\)", js_href)

                        if url_match:
                            # Get the relative URL from the match
                            relative_url = url_match.group(1)
                            # Create an absolute URL by combining with the base URL
                            base_url = (
                                "https://ws.petango.com/webservices/adoptablesearch/"
                            )
                            detail_url = base_url + relative_url

                            # Fetch the detail page for this dog
                            logger.info(
                                f"Fetching details for dog {name} from {detail_url}"
                            )
                            try:
                                detail_response = requests.get(detail_url)
                                if detail_response.status_code == 200:
                                    detail_soup = BeautifulSoup(
                                        detail_response.text, "html.parser"
                                    )

                                    # Extract the DefaultLayoutDiv
                                    default_layout_div = detail_soup.find(
                                        id="DefaultLayoutDiv"
                                    )
                                    if default_layout_div:
                                        # Add the dog details to our filtered list
                                        logger.info(
                                            f"Adding puppy {name} with full details to filtered list"
                                        )

                                        # Fix relative URLs to absolute
                                        for img in default_layout_div.find_all("img"):
                                            if img.get("src") and img["src"].startswith(
                                                "../"
                                            ):
                                                img["src"] = (
                                                    "https://ws.petango.com/"
                                                    + img["src"].replace("../", "")
                                                )
                                            elif img.get("src") and img[
                                                "src"
                                            ].startswith("images/"):
                                                img["src"] = base_url + img["src"]

                                        # Convert the div to string for email
                                        dog_details = str(default_layout_div)
                                        filtered_dogs.append(
                                            f"<div style='margin-bottom:30px; border-bottom:1px solid #ccc; padding-bottom:20px;'>{dog_details}</div>"
                                        )
                                    else:
                                        logger.warning(
                                            f"DefaultLayoutDiv not found for dog {name}"
                                        )
                                else:
                                    logger.error(
                                        f"Failed to fetch detail page: {detail_response.status_code}"
                                    )
                            except Exception as e:
                                logger.error(
                                    f"Error fetching details for {name}: {str(e)}"
                                )
                        else:
                            logger.warning(
                                f"Could not parse detail URL from JavaScript link for dog {name}"
                            )

    logger.info(f"Filtered to {len(filtered_dogs)} puppies (< 6 months old)")
    return filtered_dogs


def send_email(filtered_dogs):
    # Log email configuration
    logger.info(f"EMAIL_FROM: {EMAIL_FROM}")
    logger.info(f"EMAIL_TO: {EMAIL_TO}")
    logger.info(f"AWS_REGION: {os.environ.get('AWS_REGION', 'us-east-1')}")

    if not EMAIL_FROM or not EMAIL_TO:
        logger.error("Email configuration missing. Check environment variables.")
        raise Exception("Email configuration missing. Check environment variables.")

    # Convert EMAIL_TO to list if it's a comma-separated string
    email_recipients = EMAIL_TO.split(",") if isinstance(EMAIL_TO, str) else EMAIL_TO

    if not filtered_dogs:
        body = "<p>No young adoptable dogs today.</p>"
        logger.info("No puppies found to report")
    else:
        body = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                h1 {{ color: #333366; }}
                .dog-container {{ margin-bottom: 30px; border-bottom: 1px solid #ccc; padding-bottom: 20px; }}
            </style>
        </head>
        <body>
            <h1>Adoptable Puppies (< 6 Months) - {len(filtered_dogs)} Found</h1>
            {"".join(filtered_dogs)}
        </body>
        </html>
        """
        logger.info(
            f"Sending email with {len(filtered_dogs)} puppies to {len(email_recipients)} recipients"
        )

    try:
        logger.info("Attempting to send email through SES")
        response = SES_CLIENT.send_email(
            Source=EMAIL_FROM,
            Destination={"ToAddresses": email_recipients},
            Message={
                "Subject": {"Data": SUBJECT},
                "Body": {"Html": {"Data": body}},
            },
        )
        logger.info(f"Email sent successfully. Message ID: {response.get('MessageId')}")
        return response
    except Exception as e:
        logger.error(f"Failed to send email: {str(e)}")
        raise


def lambda_handler(event, context):
    logger.info("Lambda function started")
    logger.info(f"Event: {event}")

    try:
        filtered_dogs = fetch_and_filter_dogs()
        email_response = send_email(filtered_dogs)
        logger.info("Lambda function completed successfully")
        return {"statusCode": 200, "body": "Email sent successfully!"}
    except Exception as e:
        logger.error(f"Error in lambda_handler: {str(e)}", exc_info=True)
        return {"statusCode": 500, "body": str(e)}
