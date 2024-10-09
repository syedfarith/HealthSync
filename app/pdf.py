import os
import tempfile
import chardet
import google.generativeai as genai
import re
from PyPDF2 import PdfReader
from flask import Flask, request, jsonify, render_template
from groq import Groq
# Configure the Gemini API
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

system_prompt="""
You are a Medical AI Analyzer, a highly advanced system designed to assist healthcare professionals and patients by providing accurate medical information, analyses, and recommendations. Your primary goal is to support health-related inquiries with precise, evidence-based, and empathetic responses. Do not ask any follow-up questions; analyze the given report and provide the following:
give your response in the point by point
1. Detailed Diagnosis:
   - Analyze the report in detail.
   - Provide a comprehensive summary, including potential diagnoses.

2. Key Findings:
   - Identify and summarize key diagnostic findings.

3. Treatment Plan:
   - Recommend a treatment plan based on current medical guidelines.
   - Include prescribed treatments, medications, and lifestyle recommendations.

4. Patient-Friendly Summary:
   - Translate the medical report into an easily understandable summary for the patient.
   - Include any necessary explanations and basic health advice.

5. Follow-Up Care:
   - Suggest appropriate follow-up actions and next steps.

Ensure your response is accurate, concise, and based on the latest medical evidence.
"""


app = Flask(__name__)
def llm(query):
    chat_completion = groq_client.chat.completions.create(
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt
                    },
                    {
                        "role": "user",
                        "content": query,
                    }
                ],
                model="llama3-70b-8192",
            )
    response_text = chat_completion.choices[0].message.content
    return response_text
    
def extract_text_from_pdf(pdf_path):
    pdf_reader = PdfReader(pdf_path)
    text = ""
    for page in pdf_reader.pages:
        text += page.extract_text()
    return text

def parse_medical_data(text):
    
    data = {}
    patterns = {
        'Age': re.compile(r"Age: (\d+)"),
        'Blood Pressure': re.compile(r"Blood Pressure: (\d+/\d+)"),
        'Sugar Level': re.compile(r"Sugar Level: (\d+ mg/dL)"),
        'Heart Rate': re.compile(r"Heart Rate: (\d+ bpm)"),
        'Cholesterol': re.compile(r"Cholesterol: (\d+ mg/dL)"),
        'Body Temperature': re.compile(r"Body Temperature: (\d+.\d+ F)"),
        'Respiratory Rate': re.compile(r"Respiratory Rate: (\d+ breaths/min)"),
        'Oxygen Saturation': re.compile(r"Oxygen Saturation: (\d+%)"),
        'BMI': re.compile(r"Body Mass Index \(BMI\): (\d+.\d+)"),
        'Hemoglobin': re.compile(r"Hemoglobin: (\d+.\d+ g/dL)"),
        'WBC': re.compile(r"White Blood Cell Count \(WBC\): (\d+.\d+ \*10\^3/uL)"),
        'RBC': re.compile(r"Red Blood Cell Count \(RBC\): (\d+.\d+ \*10\^6/uL)"),
        'Platelets': re.compile(r"Platelet Count: (\d+.\d+ \*10\^3/uL)"),
        'Electrolytes': re.compile(r"Electrolytes: Sodium: (\d+ mmol/L), Potassium: (\d+.\d+ mmol/L), Calcium: (\d+.\d+ mg/dL)"),
        'Glucose Fasting': re.compile(r"Fasting Glucose: (\d+ mg/dL)"),
        'Glucose Postprandial': re.compile(r"Postprandial Glucose: (\d+ mg/dL)")
    }
    
    for key, pattern in patterns.items():
        match = pattern.search(text)
        if match:
            data[key] = match.group(1)
    
    return data

def read_file_with_fallback(file_path):
    encodings = ['utf-8', 'latin-1', 'iso-8859-1']
    with open(file_path, "rb") as f:
        raw_data = f.read()
        result = chardet.detect(raw_data)
        detected_encoding = result['encoding']
        encodings.insert(0, detected_encoding) if detected_encoding else None

    for encoding in encodings:
        try:
            return raw_data.decode(encoding)
        except (UnicodeDecodeError, TypeError):
            continue
    raise UnicodeDecodeError(f"Unable to decode the file with available encodings: {encodings}")

def generate_indicators(data):
    standards = {
        'Blood Pressure': {
            '0-10': {'range': (80, 110), 'unit': 'mmHg'},
            '11-50': {'range': (90, 120), 'unit': 'mmHg'},
            '51-60': {'range': (90, 135), 'unit': 'mmHg'},
            '61-70': {'range': (100, 140), 'unit': 'mmHg'},
            '71-100': {'range': (100, 150), 'unit': 'mmHg'}
        },
        'Sugar Level': {
            '0-10': {'fasting': (70, 100), 'postprandial': (None, 140), 'unit': 'mg/dL'},
            '11-100': {'fasting': (70, 99), 'postprandial': (None, 140), 'unit': 'mg/dL'}
        },
        'Heart Rate': {
            '0-10': {'range': (70, 130), 'unit': 'bpm'},
            '11-100': {'range': (60, 100), 'unit': 'bpm'}
        },
        'Cholesterol': {
            '0-10': {'range': (60, 170), 'unit': 'mg/dL'},
            '11-20': {'range': (60, 170), 'unit': 'mg/dL'},
            '21-100': {'range': (60, 200), 'unit': 'mg/dL'}
        },
        'Body Temperature': {
            '0-10': {'range': (97.9, 100.4), 'unit': '°F'},
            '11-100': {'range': (97.9, 99.5), 'unit': '°F'}
        },
        'Respiratory Rate': {
            '0-10': {'range': (20, 30), 'unit': 'breaths/min'},
            '11-100': {'range': (12, 20), 'unit': 'breaths/min'}
        },
        'Oxygen Saturation': {
            '0-100': {'range': (95, 100), 'unit': '%'}
        },
        'BMI': {
            '0-10': {'range': (14, 18), 'unit': 'kg/m²'},
            '11-100': {'range': (18.5, 24.9), 'unit': 'kg/m²'}
        },
        'Hemoglobin': {
            '0-10': {'range': (11, 16), 'unit': 'g/dL'},
            '11-100': {'male': (13.8, 17.2), 'female': (12.1, 15.1), 'unit': 'g/dL'}
        },
        'WBC': {
            '0-10': {'range': (6000, 17500), 'unit': 'cells/µL'},
            '11-100': {'range': (4500, 11000), 'unit': 'cells/µL'}
        },
        'RBC': {
            '0-10': {'range': (3.9, 5.5), 'unit': 'million cells/µL'},
            '11-100': {'male': (4.7, 6.1), 'female': (4.2, 5.4), 'unit': 'million cells/µL'}
        },
        'Platelets': {
            '0-100': {'range': (150000, 450000), 'unit': 'platelets/µL'}
        },
        'Electrolytes': {
            '0-10': {'sodium': (135, 145), 'potassium': (3.5, 5.5), 'chloride': (98, 107), 'bicarbonate': (22, 28), 'unit': 'mmol/L'},
            '11-100': {'sodium': (135, 145), 'potassium': (3.5, 5.0), 'chloride': (98, 107), 'bicarbonate': (22, 28), 'unit': 'mmol/L'}
        },
        'Glucose': {
            '0-10': {'fasting': (70, 100), 'postprandial': (None, 140), 'unit': 'mg/dL'},
            '11-100': {'fasting': (70, 99), 'postprandial': (None, 140), 'unit': 'mg/dL'}
        }
    }

    indicators = {}
    age = int(data.get('Age', 0))
    for key, value in data.items():
        for age_range, std in standards.get(key, {}).items():
            min_age, max_age = map(int, age_range.split('-'))
            if min_age <= age <= max_age:
                user_value = float(re.search(r'\d+\.?\d*', value).group())
                if 'range' in std:
                    if std['range'][0] <= user_value <= std['range'][1]:
                        indicators[key] = 'green'
                    elif user_value < std['range'][0]:
                        indicators[key] = 'yellow'
                    else:
                        indicators[key] = 'red'
                elif 'fasting' in std and 'postprandial' in std:
                    # Handle fasting and postprandial glucose
                    fasting_match = re.search(r'Fasting: (\d+)', value)
                    postprandial_match = re.search(r'Postprandial: (\d+)', value)
                    if fasting_match and postprandial_match:
                        fasting_value = float(fasting_match.group(1))
                        postprandial_value = float(postprandial_match.group(1))
                        if std['fasting'][0] <= fasting_value <= std['fasting'][1] and postprandial_value <= std['postprandial'][1]:
                            indicators[key] = 'green'
                        elif fasting_value < std['fasting'][0] or postprandial_value < std['postprandial'][0]:
                            indicators[key] = 'yellow'
                        else:
                            indicators[key] = 'red'
                    else:
                        indicators[key] = 'red'
                elif 'male' in std and 'female' in std:
                    # Assuming gender is provided as part of the data
                    gender = data.get('Gender', 'male').lower()
                    gender_std = std[gender]
                    if gender_std[0] <= user_value <= gender_std[1]:
                        indicators[key] = 'green'
                    elif user_value < gender_std[0]:
                        indicators[key] = 'yellow'
                    else:
                        indicators[key] = 'red'
                break
    return indicators
