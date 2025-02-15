from flask import Flask, request, jsonify, render_template
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import sys

from markdown import markdown
from langchain_ollama import OllamaLLM
from langchain_core.prompts import ChatPromptTemplate

template = """
    Answer the question below.

    here is the conversation history: {context}

    Question: {question}

    Answer:

"""

model = OllamaLLM(model="llama3")
prompt = ChatPromptTemplate.from_template(template)
chain = prompt | model
context = ''

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///chat.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class Session(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    title = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    chats = db.relationship('Chat', back_populates='session', lazy=True)

USER = True
AI = False
class Chat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('session.id'), nullable=False)
    message = db.Column(db.String(500), nullable=False)
    sender = db.Column(db.Boolean, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    session = db.relationship('Session', back_populates='chats')

    def __repr__(self):
        return f'<Chat {self.id}>'

with app.app_context():
    db.create_all()



@app.route('/')
def home():
    return render_template('index.html')


@app.route('/create_session', methods=['POST'])
def create_session():
    global context
    try:
        title = request.json.get('title', '').strip()
        
        if not title:
            title = 'Untitled Session'
        elif len(title) > 255:
            return {'error': 'Session title must be 255 characters or less'}, 400

        new_session = Session(title=title)
        db.session.add(new_session)
        db.session.flush()

        context = ""

        db.session.commit()

        return {'session_id': new_session.id, 'message': 'Session created successfully'}, 201

    except Exception as e:
        db.session.rollback()
        return {'error': f'Failed to create session: {str(e)}'}, 500


@app.route('/delete_session/<int:session_id>', methods=['DELETE'])
def delete_session(session_id):
    session = Session.query.get(session_id)
    if not session:
        return {'error': 'Session not found'}, 404

    Chat.query.filter_by(session_id=session_id).delete()
    db.session.delete(session)
    db.session.commit()
    return {'message': f'Session {session_id} and all its chats were deleted successfully'}, 200


@app.route('/send_message', methods=['POST'])
def send_message():
    global context
    session_id = request.json.get('session_id')
    message = request.json.get('message')

    if not session_id or not message:
        return {'error': 'Missing session_id or message'}, 400

    session = Session.query.get(session_id)
    if not session:
        return {'error': 'Session not found'}, 404

    try:
        user_chat = Chat(session_id=session_id, message=message, sender=USER)
        db.session.add(user_chat)

        result = chain.invoke({"rules": rules, "context": context, "question": message})
        print(result)
        print(markdown(result))
        ai_chat = Chat(session_id=session_id, message=result, sender=AI)
        db.session.add(ai_chat)

        context += f"\nUser: {message}\nAI: {result}"

        db.session.commit()

        return {'message': result}, 201

    except Exception as e:
        db.session.rollback()
        return {'error': f'Failed to process message: {str(e)}'}, 500


@app.route('/get_chats/<int:session_id>', methods=['GET'])
def get_chats(session_id):
    global context
    session = Session.query.get(session_id)
    if not session:
        return {'error': 'Session not found'}, 404

    chats_ = Chat.query.filter_by(session_id=session_id).order_by(Chat.timestamp).all()
    context = "";
    chats = [
        {
            'id': chat.id,
            'message': chat.message,
            'sender': chat.sender,
            'timestamp': chat.timestamp
        }
        for chat in chats_
    ]

    for i in range(0, len(chats), 2):
        context += f"\nUser: {chats[i]['message']}\nAI: {chats[i+1]['message']}"

    return {
        'session_id': session_id,
        'chats': chats
    }, 200

@app.route('/get_sessions', methods=['GET'])
def get_sessions():
    sessions = Session.query.order_by(Session.created_at.desc()).all()

    session_list = [
        {
            'session_id': session.id,
            'title': session.title,
            'created_at': session.created_at
        }
        for session in sessions
    ]

    return {'sessions': session_list}, 200


if __name__ == '__main__':
    app.run(debug=True)