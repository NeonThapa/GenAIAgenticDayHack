# sahayak-backend/main.py (Final Version with Gemini 1.5 Flash)

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

try:
    print("Initializing clients...")
    vertexai.init()
    db = firestore.Client()
    embedding_model = TextEmbeddingModel.from_pretrained("text-embedding-004")
    # Using the fast and cost-effective Gemini 1.5 Flash model for all generation
    generation_model = GenerativeModel("gemini-2.5-flash") 
    image_generation_model = ImageGenerationModel.from_pretrained("imagen-3.0-fast-generate-001")
    print("SUCCESS: All clients initialized.")
except Exception as e:
    print(f"CRITICAL STARTUP ERROR: {e}", file=sys.stderr)
    raise

def _get_response_text(response):
    """Safely extracts, joins, and cleans text from a model's response."""
    if not response or not response.candidates:
        print("Warning: _get_response_text received an empty or invalid response.")
        return ""
    return "".join(part.text for part in response.candidates[0].content.parts)

def _clean_json_string(text):
    """Finds and extracts the first valid JSON object from a string."""
    try:
        start = text.find('{')
        end = text.rfind('}') + 1
        if start != -1 and end != 0:
            return text[start:end]
    except Exception:
        pass
    return text

# ===================================================================
#  HELPER FUNCTIONS FOR EACH TASK
# ===================================================================

def _generate_assessment(params):
    grade = params.get('grade')
    subject = params.get('subject')
    query_text = f"General assessment questions for {grade} grade {subject}."
    
    embeddings = embedding_model.get_embeddings([query_text])
    if not embeddings: raise ValueError("Failed to generate text embedding for the query.")
    query_embedding = embeddings[0].values
    
    query = db.collection("curriculumembeddings").where("grade", "==", grade).where("subject", "==", subject).find_nearest(
        vector_field="embedding", query_vector=query_embedding, distance_measure="COSINE", limit=5
    )
    docs = query.get()
    if not docs: raise ValueError("Firestore query returned no documents.")
    
    retrieved_chunks = [doc.to_dict()['text_content'] for doc in docs if doc.exists and 'text_content' in doc.to_dict()]
    if not retrieved_chunks: raise ValueError(f"Could not find curriculum documents for Grade: '{grade}', Subject: '{subject}'.")
    context = "\n---\n".join(retrieved_chunks)
    
    prompt = f"Create a 5-question multiple-choice quiz for {grade} grade {subject}, based ONLY on this context: {context}. Your entire response must be ONLY the raw JSON object."
    response = generation_model.generate_content(prompt)
    json_text = _get_response_text(response)
    return _clean_json_string(json_text)

def _generate_worksheet(params):
    target_grade = params.get('targetGrade')
    base64_string = params.get('worksheetImageBase64')
    if not base64_string: raise ValueError("No image data provided.")
    
    image_data = base64.b64decode(base64_string)
    worksheet_image = Part.from_data(data=image_data, mime_type="image/png")
    
    prompt_for_analysis = f"Analyze the visual elements in this worksheet image. Describe a new, similar visual scene or activity appropriate for a {target_grade} student. Your description should be one concise sentence."
    analysis_response = generation_model.generate_content([worksheet_image, prompt_for_analysis])
    
    scene_description = _get_response_text(analysis_response)
    if not scene_description: raise ValueError("Could not generate a scene description from the image.")

    prompt_for_imagen = f"A clean, simple, black and white school worksheet in a fun cartoon style. The worksheet should be purely visual with no text or numbers. Draw the following scene: {scene_description}. Leave empty spaces for a teacher to write questions."
    images = image_generation_model.generate_images(prompt=prompt_for_imagen, number_of_images=1, aspect_ratio="9:16")
    
    if not images or not images[0]: raise ValueError("Imagen model failed to generate a valid image.")
    
    new_image_base64 = base64.b64encode(images[0]._image_bytes).decode('utf-8')
    return json.dumps({"new_image_base64": new_image_base64})

def _generate_lesson_plan(params):
    grade = params.get('grade')
    subject = params.get('subject')
    query_text = f"A foundational lesson plan for {grade} grade {subject}."
    
    embeddings = embedding_model.get_embeddings([query_text])
    if not embeddings: raise ValueError("Failed to generate text embedding.")
    query_embedding = embeddings[0].values
    
    query = db.collection("curriculumembeddings").where("grade", "==", grade).where("subject", "==", subject).find_nearest(
        vector_field="embedding", query_vector=query_embedding, distance_measure="COSINE", limit=5
    )
    
    docs = query.get()
    if not docs: raise ValueError("Firestore query returned no documents.")
    
    retrieved_chunks = [doc.to_dict()['text_content'] for doc in docs if doc.exists and 'text_content' in doc.to_dict()]
    if not retrieved_chunks: raise ValueError(f"Could not find curriculum documents for Grade: '{grade}', Subject: '{subject}'.")
    context = "\n---\n".join(retrieved_chunks)
    
    prompt = f"Create a detailed 45-minute lesson plan for a {grade} grade {subject} class based on this context: {context}. Your entire response must be ONLY the raw JSON object."
    response = generation_model.generate_content(prompt)
    json_text = _get_response_text(response)
    return _clean_json_string(json_text)

def _generate_creative_content(params):
    grade = params.get('grade')
    subject = params.get('subject')
    language = params.get('language', 'English')
    
    text_prompt = f"You are an expert storyteller and educator. Write a short, engaging story for a {grade} grade student to help them understand a fundamental concept in {subject}. Write the entire story in {language}, ensuring proper grammar and simple language. Use paragraphs to separate ideas."
    text_response = generation_model.generate_content(text_prompt)
    creative_text = _get_response_text(text_response)
    
    image_prompt_topic = f"a fundamental concept in {grade} grade {subject}"
    image_prompt = f"A simple, colorful illustration for a school textbook explaining '{image_prompt_topic}'. The style should be a friendly, educational cartoon suitable for children."
    
    images = image_generation_model.generate_images(prompt=image_prompt, number_of_images=1, aspect_ratio="1:1")
    
    if not images or not images[0]: 
        raise ValueError("Imagen model failed to generate a valid image.")
    
    image_base64 = base64.b64encode(images[0]._image_bytes).decode('utf-8')
    final_result = {"creative_text": creative_text, "image_base64": image_base64}
    return json.dumps(final_result)

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
        
        if task == 'generate_assessment': result = _generate_assessment(params)
        elif task == 'generate_worksheet': result = _generate_worksheet(params)
        elif task == 'generate_lesson_plan': result = _generate_lesson_plan(params)
        elif task == 'generate_creative_content': result = _generate_creative_content(params)
        else: return (f"Unknown task: '{task}'", 400, headers)
        
        return (result, 200, headers)
    except Exception as e:
        print(f"ERROR during task '{task}': {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return (f"An internal error occurred: {e}", 500, headers)