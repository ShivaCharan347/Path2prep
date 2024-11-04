import os
import re
from groq import Groq
from flask import Flask, render_template, request, redirect, url_for, flash, session, make_response
import csv




# Instantiation of Groq Client
client = Groq(api_key=os.environ.get("GROQ_APIKEY"))

app = Flask(__name__)
app.secret_key = "your_secret_key"

# Function to generate podcast conversation
def stpln_response(topic, days):
    if not topic or not days:
        return "Please enter both the topic and number of days."

    # Replace 'client' with the actual client you are using to connect with the LLM API
    llm = client.chat.completions.create(
        messages=[
            {
                "role": "system",
                "content": "You are an AI assistant helping users create structured study plans. \
                When a user provides a topic and number of days, provide a daily or weekly study plan. \
                Do not simplify the topic as if explaining to a child; instead, give detailed steps and objectives \
                for each study day or week.",
            },
            {
                "role": "user",
                "content": f"Create a study plan for the topic '{topic}' to be completed in {days} days. \
                Divide the content to be covered each day, with specific learning objectives and \
                activities or tasks for each day to ensure thorough understanding by the end of {days} days."
            }
        ],
        model="llama3-8b-8192",
    )
    
    return llm.choices[0].message.content



@app.route('/study_plan', methods=['GET', 'POST'])
def study_plan():
    answer = None
    if request.method == 'POST':
        topic = request.form.get('topic')
        days = request.form.get('days')
        if topic and days:
            answer = stpln_response(topic, days)

            # Replace **text** with <h4>text</h4> for bold text
            answer = re.sub(r'\*\*(.*?)\*\*', r'<h5>\1</h5>', answer)
            
            # Remove leading * from bullet points
            answer = re.sub(r'^\*\s*', '', answer, flags=re.MULTILINE)
            
            # Wrap the main headings
            answer = re.sub(r'## (.*?)\n', r'<h5>\1</h5>\n', answer) 
            
            answer = re.sub(r'# (.*?)\n', r'<h5>\1</h5>\n', answer)   
        else:
            answer = "Please enter both the topic and the number of days left."
    return render_template('study_plan.html', answer=answer)


def chat_response(question):
    if not question:
        return "Please enter a question."
    
    llm = client.chat.completions.create(
        messages=[
            {
                "role": "system",
                "content": "You are a helpful AI Assistant. Summarize any question or topic given by the user into no more than 5 sentences."
            },
            {
                "role": "user",
                "content": question,
            }         ],
        model="llama3-8b-8192",
    )
    
    # Limiting the response to 5 lines
    response = llm.choices[0].message.content
    summarized_response = "\n".join(response.splitlines()[:5])  # Limiting the output to 5 lines
    
    return summarized_response


@app.route('/chat', methods=['GET', 'POST'])
def chat():
    answer = None
    if request.method == 'POST':
        question = request.form.get('question')
        if question:
            answer = chat_response(question)

            # Formatting answer
            answer = re.sub(r'\*\*(.*?)\*\*', r'<h5>\1</h5>', answer)  # Bold text
            answer = re.sub(r'^\*\s*', '', answer, flags=re.MULTILINE)  # Bullet points
            answer = re.sub(r'## (.*?)\n', r'<h5>\1</h5>\n', answer)   # Headings level 2
            answer = re.sub(r'# (.*?)\n', r'<h5>\1</h5>\n', answer)    # Headings level 1
        else:
            answer = "Please enter a question."
    return render_template('chat.html', answer=answer)


@app.route('/')
def index():
    app.logger.debug("Rendering index page")
    return render_template('index.html')


@app.route('/services')
def services():
    return render_template('services.html')

# Folder to save CSV files
CSV_FOLDER = os.path.join(os.getcwd(), 'generated_quizzes')
os.makedirs(CSV_FOLDER, exist_ok=True)

# Function to get response from Groq for MCQs
def generate_mcqs(topic):
    mcq_questions = client.chat.completions.create(
        messages=[
            {
                "role": "system",
                "content": f"""
                Generate 10 multiple choice questions (MCQs) on the topic: {topic}. 
                Provide the output in the following CSV format without any headers or additional comments:
                "Question", "Option_A", "Option_B", "Option_C", "Option_D", "Correct_Answer"
                Example:
                "What is 2 + 2?", "3", "4", "5", "6", "B"
                """
            },
        ],
        model="gemma2-9b-it",
    )
    return mcq_questions.choices[0].message.content

@app.route('/mcq', methods=['GET', 'POST'])
def mcq():
    if request.method == 'POST':
        topic = request.form.get('topic')
        if topic:
            mcq_data = generate_mcqs(topic)

            if mcq_data:
                # Save the generated data to a CSV file
                filename = f"{re.sub(r'[^a-zA-Z0-9]', '_', topic)}_mcqs.csv"
                filepath = os.path.join(CSV_FOLDER, filename)
                with open(filepath, mode='w', newline='', encoding='utf-8') as file:
                    writer = csv.writer(file)

                    # Process each line and write to CSV
                    seen_rows = set()
                    for line in mcq_data.strip().split('\n'):
                        if not line.strip() or line.startswith('Let me know') or line.startswith('```'):
                            continue

                        row = [x.strip('" ') for x in line.split(',')]
                        row_tuple = tuple(row)

                        if len(row) == 6 and row_tuple not in seen_rows:
                            writer.writerow(row)
                            seen_rows.add(row_tuple)

                session['quiz_file'] = filename  # Store filename in session for next page access
                # flash("MCQs generated successfully!", "success")
                return redirect(url_for('quiz'))
            else:
                flash("Failed to generate MCQs.", "danger")
        else:
            flash("Please enter a topic to generate MCQs.", "warning")
    return render_template('mcq.html')


@app.route('/quiz', methods=['GET', 'POST'])
def quiz():
    filename = session.get('quiz_file')
    if not filename:
        flash("No quiz file found. Please generate a quiz first.", "warning")
        return redirect(url_for('mcq'))

    filepath = os.path.join(CSV_FOLDER, filename)
    questions = []
    # Read all questions from the CSV file
    with open(filepath, mode='r', encoding='utf-8') as file:
        reader = csv.reader(file)
        for row in reader:
            # Check if the row has the expected number of elements
            if len(row) == 6:
                questions.append({
                    'question': row[0],
                    'options': row[1:5],
                    'correct': row[5]
                })
    # Handle form submission
    if request.method == 'POST':
        user_answers = {}
        for index in range(1, len(questions) + 1):
            user_answers[f'q{index}'] = request.form.get(f'q{index}')

        # Calculate score and feedback
        score = calculate_score(user_answers, questions)
        feedback = generate_feedback(score, len(questions))

        # Redirect to the results page with score and feedback
        return redirect(url_for('result', score=score, feedback=feedback))

    return render_template('quiz.html', questions=questions)

# @app.route('/result')
# def result():
#     score = request.args.get('score', type=int)
#     feedback = request.args.get('feedback', default="", type=str)
    
#     return render_template('result.html', score=score, feedback=feedback)

def calculate_score(user_answers, questions):
    score = 0
    for index, question in enumerate(questions):
        correct_answer = question['correct']
        user_answer = user_answers.get(f'q{index + 1}')
        if user_answer == correct_answer:
            score += 1
    return score

def generate_feedback(score, total_questions):
    percentage = (score / total_questions) * 100
    if percentage >= 80:
        return "Excellent work! Keep it up!"
    elif percentage >= 60:
        return "Good job! A bit more practice will help you."
    else:
        return "Don't be discouraged! Review the material and try again."

    
@app.route('/result')
def result():
    score = request.args.get('score', type=int)
    feedback = request.args.get('feedback', default="")

    return render_template('result.html', score=score, feedback=feedback)




if __name__ == '__main__':
    app.run(debug=True)
