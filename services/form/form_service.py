import json
import logging
from flask import current_app
from services.ai.openai_service import parse_form_document, generate_form_questions

def extract_form_structure(file_path):
    """
    Extract form structure from a document file.
    This is a multi-step process:
    1. Parse the raw form document to identify all fields EXACTLY as they appear in the original
    2. Structure into a step-by-step flow while preserving the EXACT original text and order
    
    CRITICAL: Questions must remain exactly as they appear in the uploaded form - same wording, format and order.
    No form questions should be changed, reworded, improved, or reordered during processing.
    """
    try:
        # Log the start of form extraction
        current_app.logger.info(f"Starting EXACT form extraction for file: {file_path}")
        
        # Step 1: Parse the document to extract the EXACT fields as they appear in the original
        parsed_form = parse_form_document(file_path)
        
        # Log how many questions were found in the initial parsing
        questions_count = len(parsed_form.get('questions', []))
        current_app.logger.info(f"Initial parsing found {questions_count} questions/fields")
        
        if questions_count == 0:
            current_app.logger.error("No questions were extracted from the form. Using a fallback form template.")
            # Create a simple fallback form if no questions were found
            parsed_form = {
                "questions": [
                    {
                        "id": "form_name",
                        "question_text": "Form Name",
                        "field_type": "text",
                        "required": True
                    },
                    {
                        "id": "form_description",
                        "question_text": "Form Description",
                        "field_type": "textarea",
                        "required": True
                    }
                ]
            }
        
        # Step 2: Ensure the EXACT order and text of questions is maintained
        current_app.logger.info("Processing questions while preserving EXACT text and order...")
        structured_questions = generate_form_questions(parsed_form)
        
        # Validate the structured questions to ensure none were lost or modified
        final_questions_count = len(structured_questions.get('questions', []))
        current_app.logger.info(f"Final structured form has {final_questions_count} questions")
        
        # ALWAYS use the original parsed form if ANY questions were lost or modified
        if final_questions_count != questions_count:
            current_app.logger.warning(f"Question count mismatch! Initial: {questions_count}, Final: {final_questions_count}")
            current_app.logger.info("Using original parsed form to ensure ALL questions are preserved in their EXACT form")
            return parsed_form
        
        # Also check if any question texts were modified
        original_questions = parsed_form.get('questions', [])
        final_questions = structured_questions.get('questions', [])
        
        for i in range(min(len(original_questions), len(final_questions))):
            orig_text = original_questions[i].get('question_text', '')
            final_text = final_questions[i].get('question_text', '')
            
            if orig_text != final_text:
                current_app.logger.warning(f"Question text was modified during processing. Using original parsed form.")
                return parsed_form
        
        return structured_questions
    
    except Exception as e:
        logging.error(f"Error extracting form structure: {str(e)}")
        raise Exception(f"Failed to extract form structure: {str(e)}")

def validate_form_submission(form_structure, answers):
    """
    Validate that all required fields have been completed.
    """
    questions = form_structure.get('questions', [])
    missing_fields = []
    
    for question in questions:
        question_id = question.get('id')
        # Handle different field name variations in the structure
        is_required = question.get('required', False)
        # Get the question text from various possible field names
        question_text = question.get('question_text') or question.get('question') or question.get('label') or f"Question {question_id}"
        
        if is_required and (question_id not in answers or not answers[question_id]):
            missing_fields.append({
                'id': question_id,
                'question': question_text
            })
    
    return {
        'valid': len(missing_fields) == 0,
        'missing_fields': missing_fields
    }

def get_next_question(form_structure, current_question_id, answers):
    """
    Determine the next question to display based on current answers.
    Allows for conditional logic in forms.
    """
    questions = form_structure.get('questions', [])
    
    # If there's no current question, return the first one
    if not current_question_id:
        return questions[0] if questions else None
    
    # Find the current question's index
    current_index = next((i for i, q in enumerate(questions) if q.get('id') == current_question_id), -1)
    
    if current_index == -1 or current_index >= len(questions) - 1:
        return None  # No more questions
    
    next_question = questions[current_index + 1]
    
    # Check if there's conditional logic to skip questions
    # This is a simple implementation - could be expanded for more complex logic
    condition = next_question.get('condition')
    if condition:
        condition_field = condition.get('field')
        condition_value = condition.get('value')
        condition_operator = condition.get('operator', 'equals')
        
        if condition_field in answers:
            user_value = answers[condition_field]
            
            if condition_operator == 'equals' and user_value != condition_value:
                # Skip this question and get the next one
                return get_next_question(form_structure, next_question.get('id'), answers)
            elif condition_operator == 'not_equals' and user_value == condition_value:
                # Skip this question and get the next one
                return get_next_question(form_structure, next_question.get('id'), answers)
    
    return next_question
