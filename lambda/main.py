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

                if total_months <= 6:
                    link_element = dog.find("a")
                    img_element = dog.find("img")

                    if link_element and img_element:
                        link = link_element["href"]
                        img = img_element["src"]
                        logger.info(f"Adding puppy {name} to filtered list")
                        filtered_dogs.append(
                            f"<p><b>{name}</b> - {age_text} <br><a href='{link}'>More Info</a><br><img src='{img}' width='150'></p>"
                        )
                    else:
                        logger.warning(f"Missing link or image for dog: {name}")

    logger.info(f"Filtered to {len(filtered_dogs)} puppies (≤1 year old)")
    return filtered_dogs


def send_email(filtered_dogs):
    # Log email configuration
    logger.info(f"EMAIL_FROM: {EMAIL_FROM}")
    logger.info(f"EMAIL_TO: {EMAIL_TO}")
    logger.info(f"AWS_REGION: {os.environ.get('AWS_REGION', 'us-east-1')}")

    if not EMAIL_FROM or not EMAIL_TO:
        logger.error("Email configuration missing. Check environment variables.")
        raise Exception("Email configuration missing. Check environment variables.")

    if not filtered_dogs:
        body = "<p>No young adoptable dogs today.</p>"
        logger.info("No puppies found to report")
    else:
        body = "<h3>Adoptable Puppies (≤1 Year)</h3>" + "".join(filtered_dogs)
        logger.info(f"Sending email with {len(filtered_dogs)} puppies")

    try:
        logger.info("Attempting to send email through SES")
        response = SES_CLIENT.send_email(
            Source=EMAIL_FROM,
            Destination={"ToAddresses": [EMAIL_TO]},
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
