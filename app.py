from flask import Flask, render_template, request, redirect, url_for, session
import json
import os
import requests
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'
app.config['UPLOAD_FOLDER'] = 'static/uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Load symptom data
with open('symptom_mapping.json', 'r', encoding='utf-8') as f:
    symptom_data = json.load(f)
    # Add debug info here
    print(f"Loaded {len(symptom_data)} symptom entries")
    # Print a sample entry to debug
    if symptom_data:
        sample_key = list(symptom_data.keys())[0]
        print(f"Sample entry: {sample_key}")
        print(f"Sample value: {symptom_data[sample_key]}")

# Load labels
with open('labels.json', 'r', encoding='utf-8') as f:
    labels = json.load(f)

# ✅ Replace with your actual Google Maps API Key
API_KEY = "AIzaSyDXtAzo4kmSq5fdN12qIGZw8JT9fKj4Ccs"

def is_symptom(key, value):
    """Determine if an entry is a symptom (not a disease)"""
    # Check for common disease indicators in the key name
    disease_indicators = ["disease", "diagnosis", "syndrome", "disorder"]
    for indicator in disease_indicators:
        if indicator in key.lower():
            return False
    
    # If it has a 'is_symptom' field explicitly set to False, respect that
    if "is_symptom" in value and value["is_symptom"] is False:
        return False
        
    return True

def validate_symptom_data():
    """Validate and fix symptom_data structure to ensure symptom names are used."""
    print("Starting symptom data validation...")
    
    if not symptom_data:
        print("Warning: symptom_data is empty!")
        return
    
    # Check if the dictionary keys are symptom names
    for key, value in list(symptom_data.items()):
        # Check if this looks like a disease name instead of a symptom
        if "disease" in key.lower() or "diagnosis" in key.lower():
            print(f"Warning: Found possible disease name as key: {key}")
            
        # Make sure each entry has a mapped_term
        if "mapped_term" not in value:
            print(f"Adding mapped_term to {key}")
            value["mapped_term"] = key
            
        # For debugging, print the structure of the first few items
        if list(symptom_data.keys()).index(key) < 3:
            print(f"Sample data structure for '{key}':")
            print(f"  mapped_term: {value.get('mapped_term', 'missing')}")
            print(f"  diagnosis: {value.get('diagnosis', {}).get('en', 'missing')}")

def get_nearby_doctors(location, symptom):
    if not location:
        location = "India"  # Default fallback location

    keyword = "general physician"
    if symptom:
        symptom_lower = symptom.lower()
        if "skin" in symptom_lower:
            keyword = "dermatologist"
        elif "heart" in symptom_lower or "chest" in symptom_lower:
            keyword = "cardiologist"

    query = f"{keyword} near {location}"
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {"query": query, "key": API_KEY}

    print("📡 Google API Query:", query)

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        print("✅ Google API Response:", json.dumps(data, indent=2))
        results = data.get("results", [])[:5]
    except Exception as e:
        print(f"❌ Google API Error: {e}")
        return []

    if not results:
        print("⚠️ No results found for this query.")

    doctors = []
    for place in results:
        loc = place.get("geometry", {}).get("location", {})
        doctors.append({
            "name": place.get("name"),
            "address": place.get("formatted_address"),
            "rating": place.get("rating", "N/A"),
            "maps_url": f"https://www.google.com/maps/place/?q=place_id:{place.get('place_id')}",
            "lat": loc.get("lat"),
            "lng": loc.get("lng")
        })

    return doctors

@app.route('/')
def home():
    return render_template('language.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        lang = request.form.get('lang', 'en')
        session['lang'] = lang
        return redirect(url_for('index'))
    return render_template('login.html')

@app.route('/index')
def index():
    user_language = session.get('lang', 'en')
    localized_labels = {key: val.get(user_language, key) for key, val in labels.items()}
    
    # Create a list of symptoms only - no disease names
    symptom_list = []
    
    # Debug info - print the keys to see what's in symptom_data
    print("Available keys in symptom_data:", list(symptom_data.keys()))
    
    for key, value in symptom_data.items():
        # Skip if this is likely a disease name and not a symptom
        if not is_symptom(key, value):
            continue
        
        # Use the mapped_term (if available) as the value to be submitted
        mapped_term = value.get("mapped_term", key)
        
        # For label, use the symptom name with proper capitalization
        if user_language == 'en':
            display_label = key.capitalize()
        else:
            # For other languages, try to get translation or fallback to English
            translations = value.get("symptom_name", {})
            display_label = translations.get(user_language, key.capitalize())
        
        symptom_list.append({
            "term": mapped_term,
            "label": display_label
        })
    
    # Sort symptoms alphabetically by their display label
    symptom_list.sort(key=lambda x: x["label"])
    
    print(f"Generated symptom list with {len(symptom_list)} items")
    # Print first few items to verify they're correct
    if symptom_list:
        print("Sample symptoms:", symptom_list[:3])
    
    return render_template("index.html", labels=localized_labels, symptoms=symptom_list)

validate_symptom_data()

@app.route('/submit', methods=['POST'])
def submit():
    user_language = session.get('lang', 'en')
    name = request.form.get('name')
    age = request.form.get('age')
    gender = request.form.get('gender')
    location = request.form.get('location') or "India"
    history = request.form.get('history')
    symptoms = request.form.getlist('symptoms')

    image_file = request.files.get('image')
    image_url = None
    if image_file and image_file.filename != '':
        filename = secure_filename(image_file.filename)
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        image_file.save(image_path)
        image_url = url_for('static', filename=f'uploads/{filename}')


    matched_terms = set()
    for user_symptom in symptoms:
        for key, value in symptom_data.items():
            all_possible_names = [key.lower()] + [value.get("mapped_term", "").lower()] + [s.lower() for s in value.get("synonyms", [])]
            if user_symptom.lower() in all_possible_names:
                matched_terms.add(value.get("mapped_term", key))


    diagnosis_list = []
    precautions_list = []
    remedies_list = []
    severity_list = []

    for term in matched_terms:
        info = symptom_data.get(term)
        if info:
            diagnosis_list.append(info.get("diagnosis", {}).get(user_language, ""))
            precautions_list.extend(info.get("precautions", {}).get(user_language, []))
            remedies_list.extend(info.get("remedies", {}).get(user_language, []))
            severity_list.append(info.get("severity", "N/A"))

    fallbacks = {
        'diagnosis': {
            'en': "No diagnosis found.",
            'hi': "कोई निदान नहीं मिला।",
            'pa': "ਕੋਈ ਨਿਰੀਖਣ ਨਹੀਂ ਮਿਲਿਆ।"
        },
        'precautions': {
            'en': ["No specific precautions."],
            'hi': ["कोई विशिष्ट सावधानियां नहीं।"],
            'pa': ["ਕੋਈ ਖਾਸ ਸਾਵਧਾਨੀ ਨਹੀਂ।"]
        },
        'remedies': {
            'en': ["No specific remedies."],
            'hi': ["कोई विशेष इलाज नहीं।"],
            'pa': ["ਕੋਈ ਖਾਸ ਇਲਾਜ ਨਹੀਂ।"]
        }
    }

    primary_symptom = symptoms[0] if symptoms else ""
    nearby_doctors = get_nearby_doctors(location, primary_symptom)

    response = {
    "name": name,
    "age": age,
    "gender": gender,
    "symptoms": symptoms,
    "diagnosis": ', '.join(set(diagnosis_list)) or fallbacks['diagnosis'][user_language],
    "precautions": list(set(precautions_list)) or fallbacks['precautions'][user_language],
    "remedies": list(set(remedies_list)) or fallbacks['remedies'][user_language],
    "severity": ', '.join(set(severity_list)) or "N/A",
    "location": location,
    "doctors": nearby_doctors,
    "image_url": image_url  # ✅ This line allows the result page to show uploaded image
}


    return render_template('result.html', response=response, user_language=user_language)

@app.route('/result.html')
def result_page():
    return render_template('result.html', response={
        "diagnosis": "Please submit your symptoms first.",
        "precautions": ["No data available"],
        "remedies": ["No data available"],
        "severity": "N/A",
        "location": "",
        "doctors": []
    })

if __name__ == '__main__':
    app.run(debug=True)