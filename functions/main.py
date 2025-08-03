# functions/main.py (Cloud Function Version)

from firebase_functions import https_fn, options
from firebase_admin import initialize_app
import vertexai
from vertexai.generative_models import GenerativeModel, Part
from vertexai.language_models import TextEmbeddingModel
from vertexai.preview.vision_models import ImageGenerationModel
import base64
from google.cloud import firestore
import json

# Initialize Firebase and Vertex AI
initialize_app()
vertexai.init()
db = firestore.Client()

# Initialize models
embedding_model = TextEmbeddingModel.from_pretrained("text-embedding-004")
generation_model = GenerativeModel("gemini-1.5-flash-preview-0514")
image_generation_model = ImageGenerationModel.from_pretrained("imagen-3.0-generate-001")

# This is your main backend function, now wrapped as a Cloud Function
@https_fn.on_request(cors=options.CorsOptions(cors_origins="*", cors_methods=["get", "post"]))
def sahayak_agent_router(req: https_fn.Request) -> https_fn.Response:
    try:
        # Note: The task is now passed in the request body, not as a query parameter
        request_json = req.get_json(silent=True)
        if not request_json:
            return https_fn.Response("Invalid JSON body.", status=400)

        task = request_json.get('task')
        params = request_json.get('params', {})
        
        result = ""
        if task == 'generate_assessment':
            result = _generate_assessment(params)
        # Add other tasks here as you build them
        # elif task == 'generate_worksheet':
        #     result = _generate_worksheet(params)
        else:
            return https_fn.Response(f"Unknown task: '{task}'", status=400)
        
        return https_fn.Response(result, status=200, headers={"Content-Type": "application/json"})

    except Exception as e:
        print(f"ERROR during task '{task}': {e}")
        return https_fn.Response(f"An internal error occurred: {e}", status=500)

# --- Helper function to generate an assessment ---
def _generate_assessment(params):
    grade = params.get('grade')
    subject = params.get('subject')
    if not grade or not subject:
        raise ValueError("Missing 'grade' or 'subject' in parameters.")
        
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
    
    # Safely extract and clean the JSON from the response
    raw_text = "".join(part.text for part in response.candidates[0].content.parts)
    start = raw_text.find('{')
    end = raw_text.rfind('}') + 1
    if start != -1 and end != 0:
        return raw_text[start:end]
    return raw_text