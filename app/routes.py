from flask import Blueprint, request, redirect, url_for, flash, send_from_directory, render_template, current_app, jsonify
from werkzeug.utils import secure_filename
import os
from app import db, bcrypt
from app.models import FileRecord, User
from app.forms import RegistrationForm, LoginForm,UpdateAccountForm
from flask_login import login_user, current_user, logout_user, login_required
from pdf2image import convert_from_path
from langdetect import detect
from deep_translator import GoogleTranslator
import google.generativeai as genai
from groq import Groq
import uuid
import tempfile
import secrets
from PIL import Image

main = Blueprint('main', __name__)

def allowed_file(filename):
    allowed_extensions = current_app.config.get('ALLOWED_EXTENSIONS', {'png', 'jpg', 'jpeg', 'gif', 'pdf'})
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

def convert_pdf_to_image(pdf_path, output_folder, output_filename):
    images = convert_from_path(pdf_path, poppler_path=r'C:\poppler-24.02.0\Library\bin')
    image_filename = f"{output_filename}.png"
    image_path = os.path.join(output_folder, image_filename)
    if images:
        images[0].save(image_path, 'PNG')
    return image_filename

def save_picture(form_picture):
    random_hex = secrets.token_hex(8)
    _, f_ext = os.path.splitext(form_picture.filename)
    picture_fn = random_hex + f_ext
    picture_path = os.path.join(current_app.root_path, 'static/profile_pics', picture_fn)
    
    output_size = (125, 125)
    i = Image.open(form_picture)
    i.thumbnail(output_size)
    i.save(picture_path)

    return picture_fn

@main.route('/')
@main.route('/home')
def home():
    return render_template('home.html')

@main.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))
    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        if form.picture.data:
            picture_file = save_picture(form.picture.data)
        else:
            picture_file = 'default.png'
        user = User(
            username=form.username.data,
            email=form.email.data,
            password=hashed_password,
            phone_number=form.phone_number.data,
            age=form.age.data,
            gender=form.gender.data,
            city=form.city.data,
            state=form.state.data,
            country=form.country.data,
            abha_id=form.abha_id.data,
            abha_address=form.abha_address.data,
            image_file=picture_file  # Assuming you have a default image for new users
        )        
        db.session.add(user)
        db.session.commit()
        flash('Your account has been created! You are now able to log in', 'success')
        return redirect(url_for('main.login'))
    return render_template('register.html', form=form)

@main.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and bcrypt.check_password_hash(user.password, form.password.data):
            login_user(user, remember=form.remember.data)
            return redirect(url_for('main.home'))
        else:
            flash('Login Unsuccessful. Please check email and password', 'danger')
    return render_template('login.html', form=form)

@main.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('main.home'))

@main.route('/uploads/<filename>')
@login_required
def uploaded_file(filename):
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)

@main.route('/delete/<int:file_id>', methods=['POST'])
@login_required
def delete_file(file_id):
    record = FileRecord.query.get(file_id)
    if record and record.owner == current_user:
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], record.filename)
        if os.path.exists(file_path):
            os.remove(file_path)
        db.session.delete(record)
        db.session.commit()
        flash('File successfully deleted')
    return redirect(url_for('main.index'))

@main.route('/index', methods=['GET', 'POST'])
@login_required
def index():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            if filename.lower().endswith('.pdf'):
                image_filename = convert_pdf_to_image(filepath, current_app.config['UPLOAD_FOLDER'], filename.rsplit('.', 1)[0])
                new_record = FileRecord(filename=image_filename, filepath=filename, owner=current_user)
            else:
                new_record = FileRecord(filename=filename, filepath=filename, owner=current_user)
                
            db.session.add(new_record)
            db.session.commit()
            flash('File successfully uploaded')
            return redirect(url_for('main.index'))
    records = FileRecord.query.filter_by(owner=current_user).all()
    return render_template('index.html', records=records)

# Chatbot functionality
system_prompt1="""

Your are an ai chatbot MedQuery your jobs is to solve the user's medical related query.
You should not ask any followup questions
you should give the clear and easy to understanding explanation to the human.
You should not answer to the question other than medical query 
You should not ask any personal question to the user.

"""
def is_medical_query(query):
    from app.medical_keywords import medical_keywords 
    return any(keyword in query.lower() for keyword in medical_keywords)

@main.route('/chatbot', methods=['GET'])
def chatbot_home():
    return render_template('chat.html')

@main.route('/chat', methods=['POST'])
def chat():
    genai.configure(api_key=current_app.config['GOOGLE_API_KEY'])
    groq_client = Groq(api_key=current_app.config['GROQ_API_KEY'])

    data = request.json
    query = data.get("message", "")
    selected_model = data.get("model", "gemini-1.5-flash-latest")

    detected_language = detect(query)
    
    if detected_language != "en":
        query = GoogleTranslator(source=detected_language, target="en").translate(query)

    if query.lower() == "who are you":
        response_text = "My name is MedQuery. I am here to help you. How can I help you?"
    else:
        if not is_medical_query(query):
            return jsonify({"error": "Please enter a medical-related query."}), 400

        try:
            if "gemini" in selected_model:
                gemini_generation_config = {
                    "temperature": 1,
                    "top_p": 0.95,
                    "top_k": 64,
                    "max_output_tokens": 8192,
                    "response_mime_type": "text/plain",
                }

                safety_settings = [
                    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
                ]

                gemini_model = genai.GenerativeModel(
                    model_name="gemini-1.5-flash-latest",
                    safety_settings=safety_settings,
                    generation_config=gemini_generation_config,
                )

                chat_session = gemini_model.start_chat(history=[])
                response = chat_session.send_message(query)
                response_text = response.text
            else:
                chat_completion = groq_client.chat.completions.create(
                    messages=[
                        {
                            "role": "system",
                            "content": system_prompt1,
                        },
                        {
                            "role": "user",
                            "content": query,
                        }
                    ],
                    model=selected_model,
                )
                response_text = chat_completion.choices[0].message.content

        except Exception as e:
            response_text = f"An error occurred: {str(e)}"

    if detected_language != "en":
        response_text = GoogleTranslator(source="en", target=detected_language).translate(response_text)

    return jsonify({"response": response_text})

from app.pdf import *

@main.route('/pdf')
def pdf_analysis():
    return render_template('analysis.html')

@main.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400

    file = request.files['file']

    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    if file:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
            file_path = tmp_file.name
            file.save(file_path)

        if file.mimetype == 'application/pdf':
            text = extract_text_from_pdf(file_path)
        else:
            text = read_file_with_fallback(file_path)

        medical_data = parse_medical_data(text)
        response=llm(str(medical_data))
        print(response)
        
        os.remove(file_path)
        
        return jsonify({"response": response})

    return jsonify({"error": "File processing failed"}), 500


@main.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            try:
                if filename.lower().endswith('.pdf'):
                    text = extract_text_from_pdf(filepath)
                else:
                    text = read_file_with_fallback(filepath)

                medical_data = parse_medical_data(text)
                indicators = generate_indicators(medical_data)
                os.remove(filepath)

                return jsonify({"medical_data": medical_data, "indicators": indicators})

            except Exception as e:
                os.remove(filepath)
                flash('An error occurred while processing the file')
                return redirect(request.url)

    return render_template('dashboard.html')


@main.route("/account", methods=['GET', 'POST'])
@login_required
def account():
    form = UpdateAccountForm()
    if form.validate_on_submit():
        current_user.username = form.username.data
        current_user.email = form.email.data
        current_user.phone_number = form.phone_number.data
        current_user.age = form.age.data
        current_user.gender = form.gender.data
        current_user.city = form.city.data
        current_user.state = form.state.data
        current_user.country = form.country.data
        current_user.abha_id = form.abha_id.data
        current_user.abha_address = form.abha_address.data
        db.session.commit()
        flash('Your account has been updated!', 'success')
        return redirect(url_for('main.account'))
    elif request.method == 'GET':
        form.username.data = current_user.username
        form.email.data = current_user.email
        form.phone_number.data = current_user.phone_number
        form.age.data = current_user.age
        form.gender.data = current_user.gender
        form.city.data = current_user.city
        form.state.data = current_user.state
        form.country.data = current_user.country
        form.abha_id.data = current_user.abha_id
        form.abha_address.data = current_user.abha_address
    return render_template('account.html', title='Account', form=form)


# Configure the generative AI model
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

generation_config = {
    "temperature": 1,
    "top_p": 0.95,
    "top_k": 64,
    "max_output_tokens": 8192,
    "response_mime_type": "text/plain",
}

safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
]

model = genai.GenerativeModel(
    model_name="gemini-1.5-flash-latest",
    safety_settings=safety_settings,
    generation_config=generation_config,
)

@main.route('/med')
def med():
    return render_template('disease.html')

@main.route('/disease', methods=['POST'])
def disease():
    data = request.json
    print(data)
    predicted_class = data['predicted_class']
    if predicted_class == 'notumor':
        content="You are perfectly alright"
    # Generate content about the predicted class
    else:
        chat_session = model.start_chat(history=[])

        response = chat_session.send_message(f"Tell me about {predicted_class}.but don't tell disclaimer that consult to doctor.dont tell any additiona note like that")
        content = response.text

    return jsonify({"content": content})

if __name__ == '__main__':
    app.run(debug=True)


