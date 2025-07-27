import functions_framework
import vertexai
from vertexai.generative_models import GenerativeModel, Part
from vertexai.language_models import TextEmbeddingModel
from vertexai.preview.vision_models import ImageGenerationModel
import base64
from google.cloud import firestore
import os
import sys
import json
# --- ADDED MISSING IMPORTS ---
from urllib.parse import urlencode
from datetime import datetime, timedelta

try:
    print("Initializing clients...")
    vertexai.init()
    db = firestore.Client()
    embedding_model = TextEmbeddingModel.from_pretrained("text-embedding-004")
    # Note: I am reverting to the stable gemini-pro models to avoid potential access issues.
    # If gemini-2.5-pro is working for you, you can change this back.
    text_generation_model = GenerativeModel("gemini-2.5-pro")
    vision_generation_model = GenerativeModel("gemini-2.5-pro")
    image_generation_model = ImageGenerationModel.from_pretrained("imagen-3.0-generate-002")
    print("SUCCESS: All clients initialized.")
except Exception as e:
    print(f"CRITICAL STARTUP ERROR: {e}", file=sys.stderr)
    raise

def _get_response_text(response):
    if not response.candidates: return ""
    raw_text = "".join(part.text for part in response.candidates[0].content.parts)
    try:
        start = raw_text.find('{'); end = raw_text.rfind('}') + 1
        if start != -1 and end != 0: return raw_text[start:end]
    except Exception: pass
    return raw_text

# ===================================================================
#  HELPER FUNCTIONS FOR EACH TASK
# ===================================================================

def _generate_assessment(params):
    # --- CORRECTED: Removed duplicate code ---
    grade = params.get('grade')
    subject = params.get('subject')
    query_text = f"General assessment questions for {grade} grade {subject}."
    
    embeddings = embedding_model.get_embeddings([query_text])
    if not embeddings: raise ValueError("Failed to generate text embedding.")
    query_embedding = embeddings[0].values
    
    query = db.collection("curriculumembeddings").where("grade", "==", grade).where("subject", "==", subject).find_nearest(
        vector_field="embedding", 
        query_vector=query_embedding, 
        distance_measure="COSINE", # Using COSINE as per last fix
        limit=5
    )
    
    retrieved_chunks = [doc.to_dict()['text_content'] for doc in query.get() if doc.exists and 'text_content' in doc.to_dict()]
    if not retrieved_chunks: raise ValueError(f"Could not find curriculum documents for Grade: '{grade}', Subject: '{subject}'.")
    context = "\n---\n".join(retrieved_chunks)
    
    prompt = f"Create a 5-question multiple-choice quiz for {grade} grade {subject}, based ONLY on this context: {context}. Your entire response must be ONLY the raw JSON object."
    response = text_generation_model.generate_content(prompt)
    return _get_response_text(response)
    
def _generate_worksheet(params):
    # This function is a placeholder/simulation as per previous steps
    target_grade = params.get('targetGrade')
    prompt = f"""Rewrite these math questions to be suitable for a {target_grade}: "Question 1: If you have 3 apples and get 2 more, how many apples do you have?". Format as a JSON object with a key "new_questions"."""
    response = text_generation_model.generate_content(prompt)
    return _get_response_text(response)
    
def _generate_lesson_plan(params):
    # --- THIS IS THE TARGETED UPDATE ---
    grade = params.get('grade')
    subject = params.get('subject')
    # Get the teacher's email from the parameters sent by the front-end
    teacher_email = params.get('email') 

    query_text = f"A foundational lesson plan for {grade} grade {subject}."
    embeddings = embedding_model.get_embeddings([query_text])
    if not embeddings: raise ValueError("Failed to generate text embedding.")
    query_embedding = embeddings[0].values
    
    query = db.collection("curriculumembeddings").where("grade", "==", grade).where("subject", "==", subject).find_nearest(
        vector_field="embedding", 
        query_vector=query_embedding, 
        distance_measure="COSINE", 
        limit=5
    )
    
    retrieved_chunks = [doc.to_dict()['text_content'] for doc in query.get() if doc.exists and 'text_content' in doc.to_dict()]
    if not retrieved_chunks: raise ValueError(f"Could not find curriculum documents for Grade: '{grade}', Subject: '{subject}'.")
    context = "\n---\n".join(retrieved_chunks)
    
    prompt = f"Create a detailed 45-minute lesson plan for a {grade} grade {subject} class based on this context: {context}. Your entire response must be ONLY the raw JSON object."
    response = text_generation_model.generate_content(prompt)
    
    lesson_plan_text = _get_response_text(response)
    lesson_plan_data = json.loads(lesson_plan_text)
    
    # --- UPDATE CALENDAR LINK LOGIC ---
    start_time = datetime.now() + timedelta(days=1)
    start_time = start_time.replace(hour=9, minute=0, second=0, microsecond=0)
    end_time = start_time + timedelta(hours=1)
    dates = f"{start_time.strftime('%Y%m%dT%H%M%S')}/{end_time.strftime('%Y%m%dT%H%M%S')}"
    
    details = f"Generated Lesson Plan:\n\n"
    for key, value in lesson_plan_data.items():
        formatted_key = key.replace('_', ' ').title()
        details += f"{formatted_key}:\n{value}\n\n"
    
    calendar_params = {
        'action': 'TEMPLATE', 
        'text': f"Lesson Plan: {grade} {subject}", 
        'dates': dates, 
        'details': details
    }
    # Add the teacher's email as an attendee to the calendar invite
    if teacher_email:
        calendar_params['add'] = teacher_email

    lesson_plan_data['calendar_link'] = f"https://www.google.com/calendar/render?{urlencode(calendar_params)}"
    
    # --- SIMULATE SENDING EMAIL ---
    if teacher_email:
        _send_email_notification({
            'email': teacher_email,
            'grade': grade,
            'subject': subject,
            'lesson_plan': lesson_plan_data
        })
    
    return json.dumps(lesson_plan_data)

def _generate_creative_content(params):
    grade = params.get('grade')
    subject = params.get('subject')
    # --- NEW: Get the selected language ---
    language = params.get('language', 'English') # Default to English if not provided

    # --- NEW: Update the prompt to include the language ---
    text_prompt = f"Write a short, engaging story for a {grade} grade student to help them understand a fundamental concept in {subject}. Please write the entire story in {language}."
    
    text_response = text_generation_model.generate_content(text_prompt)
    creative_text = _get_response_text(text_response)

    # --- NEW: Update the image prompt to describe the scene in English for the model ---
    # The image model itself works best with English prompts, but the *content* can be universal.
    image_prompt_topic = f"a fundamental concept in {grade} grade {subject}"
    image_prompt = f"A simple, colorful illustration for a school textbook explaining '{image_prompt_topic}'. The style should be a friendly, educational cartoon style suitable for children."
    
    images = image_generation_model.generate_images(prompt=image_prompt, number_of_images=1, aspect_ratio="1:1")
    if not images: raise ValueError("Imagen model failed to generate any images.")
    
    image_base64 = base64.b64encode(images[0]._image_bytes).decode('utf-8')
    final_result = {"creative_text": creative_text, "image_base64": image_base64}
    return json.dumps(final_result)

def _send_email_notification(params):
    # This remains a simulation as real email sending is complex
    to_email = params.get('email')
    grade = params.get('grade')
    subject = params.get('subject')
    lesson_plan_data = params.get('lesson_plan')
    if not to_email or not lesson_plan_data: raise ValueError("Missing email or lesson plan data.")
    email_subject = f"Your Generated Lesson Plan: {grade} {subject}"
    email_body = "Here is the lesson plan you generated with Shiksha AI:\n\n"
    for key, value in lesson_plan_data.items():
        if key == 'calendar_link': continue # Don't include the link in the email body
        formatted_key = key.replace('_', ' ').title()
        email_body += f"--- {formatted_key} ---\n{value}\n\n"
    print(f"--- SIMULATING EMAIL ---")
    print(f"To: {to_email}")
    print(f"Subject: {email_subject}")
    print(f"Body:\n{email_body}")
    print(f"--- END SIMULATION ---")
    # In a real app, you would return a success message here.
    # We are handling this inside the lesson planner now.

# ===================================================================
#  MAIN CLOUD FUNCTION (THE ROUTER)
# ===================================================================
@functions_framework.http
def sahayak_agent_router(request):
    if request.method == 'OPTIONS':
        headers = {'Access-Control-Allow-Origin': '*','Access-Control-Allow-Methods': 'POST, OPTIONS','Access-Control-Allow-Headers': 'Content-Type, Authorization','Access-Control-Max-Age': '3600'}
        return ('', 204, headers)
    headers = {'Access-Control-Allow-Origin': '*'}
    task = ''
    try:
        request_json = request.get_json(silent=True)
        if not request_json: return ('Invalid JSON body.', 400, headers)
        task = request_json.get('task')
        params = request_json.get('params', {})
        
        # NOTE: We no longer need the 'send_email' task here, it's handled inside the lesson planner
        if task == 'generate_assessment': result = _generate_assessment(params)
        elif task == 'generate_worksheet': result = _generate_worksheet(params)
        elif task == 'generate_lesson_plan': result = _generate_lesson_plan(params)
        elif task == 'generate_creative_content': result = _generate_creative_content(params)
        else: return (f"Unknown task: '{task}'", 400, headers)
        
        return (result, 200, headers)
    except Exception as e:
        print(f"ERROR during task '{task}': {e}", file=sys.stderr)
        return (f"An internal error occurred: {e}", 500, headers)