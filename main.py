from datetime import datetime
import hashlib
import random
import string

from flask import Flask, render_template, redirect, url_for, request, abort, jsonify, flash
from flask_socketio import SocketIO, emit, join_room
from flask_login import (
 LoginManager,
 login_user,
 logout_user,
 login_required,
 current_user,
 UserMixin,
)
from flask_sqlalchemy import SQLAlchemy

# from models import User, Conversation, Message

app = Flask(__name__)
app.config["SECRET_KEY"] = "mY-sUp3r-s3cr37-k3y-lol"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///database.sqlite"
app.config["SESSION_COOKIE_NAME"] = "your_session_cookie_name_here"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Strict"
app.config["SESSION_COOKIE_ENCODING"] = "utf-8"
socketio = SocketIO(app)
login_manager = LoginManager()
login_manager.init_app(app)
user_ids = []
db = SQLAlchemy(app)


def generate_uid():
	uid = "".join(random.choices(string.digits, k=5))
	return int(uid)


class User(UserMixin, db.Model):
    __tablename__ = "user"
    id = db.Column(db.Integer, primary_key=True, default=generate_uid)
    name = db.Column(db.String(64), index=True, unique=True)
    email = db.Column(db.String(120), index=True, unique=True)
    password = db.Column(db.String(128))
    conversations = db.relationship("Conversation",
                                    backref="user",
                                    lazy="dynamic")
    sent_messages = db.relationship("Message",
                                    foreign_keys="Message.sender_id",
                                    backref="sender",
                                    lazy="dynamic")
    received_messages = db.relationship(
        "Message",
        foreign_keys="Message.receiver_id",
        backref="receiver",
        lazy="dynamic",
    )
    settings = db.Column(db.JSON)

    def __repr__(self):
        return "<User {}>".format(self.name)


class Conversation(db.Model):
	__tablename__ = "conversation"
	id = db.Column(db.Integer, primary_key=True)
	#title = db.Column(db.String(255))
	user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
	messages = db.relationship("Message", backref="conversation", lazy="dynamic")

	def __repr__(self):
		return "<Conversation {}>".format(self.title)


class Message(db.Model):
	__tablename__ = "message"
	id = db.Column(db.Integer, primary_key=True)
	text = db.Column(db.Text)
	timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)

	sender_id = db.Column(db.Integer, db.ForeignKey("user.id"))
	receiver_id = db.Column(db.Integer, db.ForeignKey("user.id"))
	conversation_id = db.Column(db.String, db.ForeignKey("conversation.id"))

	def __repr__(self):
		return "<Message {}>".format(self.text)


@login_manager.user_loader
def load_user(user_id):
	return User.query.get(int(user_id))


@login_manager.unauthorized_handler
def unauthorized():
	return redirect(url_for("login"))


@app.before_first_request
def create_tables():
	print("Databases created.")
	db.create_all()
	# user = User(name="admin1", email="admin1@12345.com", password="12345")
	# print(user)
	# db.session.add(user)
	# db.session.commit()


@app.route("/")
def index():
	return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
	if request.method == "POST":
		username = str(request.form["username"])
		password = str(request.form["password"])
		user = User.query.filter_by(name=username).first()
		if user is not None and user.password == password:
			print(type(user.name))
			print("Logged in!", login_user(user, remember=True))
			return redirect(url_for("chat_list"))
		else:
			return abort(401)
	else:
		return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
	if request.method == "POST":
		username = request.form["username"]
		password = request.form["password"]
		email = request.form["email"]
		new_user = User(name=username, password=password, email=email)
		db.session.add(new_user)
		db.session.commit()
		return redirect(url_for("login"))
	else:
		return render_template("register.html")


@app.route("/logout")
@login_required
def logout():
	logout_user()
	return redirect(url_for("index"))


@app.route("/protected")
@login_required
def protected():
	return render_template("protected.html")


@app.route("/profile")
@login_required
def profile():
	users = User.query.all()
	return render_template("profile.html", user=current_user, users=users)


@app.route("/edit_profile", methods=["GET", "POST"])
@login_required
def edit_profile():
	if request.method == "POST":
		user = User.query.filter_by(id=current_user.id).first()
		user.name = request.form["name"]
		user.email = request.form["email"]
		receive_notification = request.form.get('receive_notification')
		if receive_notification == 'True':
		  receive_notification = True
		elif receive_notification == 'False':
		  receive_notification = False
		else:
		  receive_notification = None
		settings = {}
		settings['receive_notification'] = receive_notification
		db.session.commit()
		return redirect(url_for("profile"))
	else:
		return render_template("edit_profile.html", user=current_user)


def get_conversations_for_user(user):
	conversations = Conversation.query.filter_by(user_id=user.id).all()
	return conversations


@app.route('/delete-users')
@login_required
def delete_users():
	users_to_keep = ['Durgesh™', 'Muditabhalerao']
	deleted_users = []
	users_to_delete = User.query.filter(User.name.notin_(users_to_keep)).all()
	for user in users_to_delete:
		print(user)
		deleted_users.append(user.name)
		db.session.delete(user)
	db.session.commit()
	return jsonify({"message": f"{len(deleted_users)} Accounts deleted.", "deleted_accounts": deleted_users})


@app.route("/search-users")
@login_required
def search_users():
	search_term = request.args.get("q")
	if search_term == "":
		users = User.query.all()
	else:
		users = User.query.filter(User.name.ilike(f"%{search_term}%")).all()
	if len(users) == 0:
		return jsonify([{"id": "", "username": "User Not Found!"}])
	return jsonify([{"id": user.id, "username": user.name} for user in users])


@app.route("/chat/")
@login_required
def redirect_from_chat_list():
	return redirect(url_for('chat_list'))


@app.route("/chat")
@login_required
def chat_list():
	users = User.query.all()
	return render_template('chat_list.html',
	                       users=users,
	                       current_user=current_user)


@app.route("/chat/<recipient_id>")
@login_required
def chat(recipient_id):
	global user_ids
	recipient = User.query.get(recipient_id)
	# room, user_ids = get_room(current_user.id, recipient_id)
	room = get_room(current_user.id, recipient_id)[0]
	# messages = Message.query.filter_by(room=room).order_by(Message.timestamp).all()
	print("Room: ", room, "Recipient: ", recipient.name)
	return render_template(
	 "chat.html",
	 recipient=recipient,
	 room=room,
	 receiver_username=recipient.name,
	 sender_username=current_user.name,
	 messages=["I'm", " Justa", "Empty", " list."],
	)

@app.route('/messages/<room_id>/getlastmsgtimestamp')
@login_required
def get_last_msg_timestamp(room_id):
    limit = request.args.get('limit', default=50, type=int)
    offset = request.args.get('offset', default=0, type=int)
    last_message_timestamp = request.args.get('last_message_timestamp', type=str)
    if last_message_timestamp:
        last_message_timestamp = datetime.fromisoformat(last_message_timestamp)
        messages = Message.query.filter(
            Message.conversation_id == room_id,
            Message.timestamp > last_message_timestamp
        ).order_by(Message.timestamp.desc()).limit(limit).offset(offset)
    else:
        messages = Message.query.filter_by(
            conversation_id=room_id
        ).order_by(Message.timestamp.desc()).limit(limit).offset(offset)
    message_list = []
    for message in messages:
        message_list.append({
            "timestamp": message.timestamp.isoformat()
        })
    if len(message_list) == 0:
      return jsonify({'message': 'No more messages to fetch.'})
    message_list.reverse()
    if current_user.id in [message.sender_id, message.receiver_id]:
        return jsonify(messages=message_list), 200
    else:
        return jsonify({'message': 'unauthorized.'}), 401


@app.route('/messages/<room_id>/fetch')
@login_required
def get_messages(room_id):
    limit = request.args.get('limit', default=50, type=int)
    offset = request.args.get('offset', default=0, type=int)
    last_message_timestamp = request.args.get('last_message_timestamp', type=str)
    if last_message_timestamp:
        last_message_timestamp = datetime.fromisoformat(last_message_timestamp)
        messages = Message.query.filter(
            Message.conversation_id == room_id,
            Message.timestamp > last_message_timestamp
        ).order_by(Message.timestamp.desc()).limit(limit).offset(offset)
    else:
        messages = Message.query.filter_by(
            conversation_id=room_id
        ).order_by(Message.timestamp.desc()).limit(limit).offset(offset)
    message_list = []
    for message in messages:
        message_list.append({
            "id": message.id,
            "sender": message.sender.name,
            "text": message.text,
            "timestamp": message.timestamp.isoformat()
        })
    if len(message_list) == 0:
      return jsonify({'message': 'No more messages to fetch.'})
    message_list.reverse()
    if current_user.id in [message.sender_id, message.receiver_id]:
        return jsonify(messages=message_list), 200
    else:
        return jsonify({'message': 'unauthorized.'}), 401


@app.route('/messages/<room_id>/delete', methods=['GET'])
@login_required
def delete_messages(room_id):
	messages = Message.query.filter_by(conversation_id=room_id)
	if messages is None:
		return jsonify({'success': False})
	messages.delete()
	db.session.commit()
	return jsonify({'success': True})


@socketio.on("join")
def on_join(data):
	room = data["room"]
	print("Server (join): ", data)
	join_room(room)
	emit("status", current_user.name + " has entered the room.", room=room)


@socketio.on('status')
def handle_status_event(data):
	room = data['room']
	message = data['message']
	status = data['status']
	username = data['username']
	emit('status', {
	 'message': message,
	 'status': status,
	 'username': username
	},
	     room=room)


@socketio.on("message")
def send_message(data):
	user = User.query.filter_by(name=str(current_user.name)).first()
	receiver = User.query.filter_by(name=str(data['receiver'])).first()
	room = str(data['room'])
	message = Message(text=data['message'],
	                  sender_id=user.id,
	                  receiver_id=receiver.id,
	                  conversation_id=room)
	print("(Server) message event: ", data)
	print("Message object: ", message.id, message.text, message.sender_id,
	      message.receiver_id, message.conversation_id)
	db.session.add(message)
	db.session.commit()
	message = Message.query.order_by(Message.id.desc()).first()
	emit(
	 "receive_message",
	 {
	  "sender": data['sender'],
	  "message": data["message"],
		"timestamp": message.timestamp if message else ""
	 },
	 room=data["room"],
	)


def get_room(user1_id, user2_id):
	user1_id = str(user1_id)
	user2_id = str(user2_id)
	if user1_id > user2_id:
		user1_id, user2_id = user2_id, user1_id
	room_id = hashlib.sha256((user1_id + user2_id).encode()).hexdigest()
	return room_id, [user1_id, user2_id]


if __name__ == "__main__":
	with app.app_context():
		db.create_all()
	socketio.run(app, host="0.0.0.0", port=8000, debug=True)
