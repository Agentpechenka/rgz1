from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_jwt_extended import JWTManager, create_access_token, jwt_required, get_jwt_identity, get_jwt
from flask_bcrypt import Bcrypt
from moviepy import VideoFileClip
from models import db, Video, User, Comment
import os, json

app = Flask(__name__)
app.config['JWT_SECRET_KEY'] = os.getenv("JWT_SECRET_KEY", "971080efa0f26c1ce9585e72c5d0ce1fe4624ba5a4c4dd56771a9aaa36ee1310")
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///data.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
jwt = JWTManager(app)
bcrypt = Bcrypt(app)
db.init_app(app)
CORS(app)

@app.route('/api/user/videos', methods=['GET'])
@jwt_required()
def user_videos():
    current_user_id = int(get_jwt_identity())
    videos = Video.query.filter_by(user_id=current_user_id).all()
    if not videos:
        return jsonify([]), 200
    return jsonify([{
        "id": video.id,
        "title": video.title,
        "description": video.description,
        "url": video.url,
        "preview": video.preview
    } for video in videos])

@app.route('/get_preview|<string:name>', methods=['GET'])
def get_pic(name):
    return send_from_directory("media/previews", f"{name}.png")

@app.route('/get_video|<string:name>', methods=['GET'])
def get_video(name):
    return send_from_directory("media/videos", f"{name}.mp4")

@app.route('/get_pic/<string:name>', methods=['GET'])
def get_pics(name):
    return send_from_directory("media/img", f"{name}")

@app.route('/register', methods=['POST'])
def register():
    data = json.loads(request.get_json()["body"])
    if not data or not all(k in data for k in ("nickname", "email", "password")):
        return jsonify({"error": "Invalid data"}), 400
    hashed_password = bcrypt.generate_password_hash(data['password']).decode('utf-8')
    new_user = User(username=data['nickname'], email=data['email'], password=hashed_password)
    try:
        db.session.add(new_user)
        db.session.commit()
    except Exception:
        return jsonify({"error": "User already exists"}), 409
    return jsonify({"message": "User registered successfully"}), 201

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    if not data or not all(k in data for k in ("email", "password")):
        return jsonify({"error": "Invalid data"}), 400
    user = User.query.filter_by(email=data['email']).first()
    if not user or not bcrypt.check_password_hash(user.password, data['password']):
        return jsonify({"error": "Invalid email or password"}), 401
    access_token = create_access_token(identity=str(user.id), additional_claims={"username": user.username, "email": user.email})
    return jsonify({"access_token": access_token}), 200

@app.route('/api/user/profile', methods=['GET'])
@jwt_required()
def get_user_profile():
    user = get_jwt_identity()
    user_data = User.query.filter_by(id=user).first()
    if user_data:
        return jsonify({
            "username": user_data.username,
            "email": user_data.email
        }), 200
    return jsonify({"error": "User not found"}), 404


URL_FOLDER = 'media/videos'
URLP_FOLDER = 'media/previews'
@app.route('/api/user/upload', methods=['POST'])
@jwt_required()
def upload_video():
    user_id = get_jwt_identity()
    if 'video' not in request.files:
        return jsonify({"error": "No video file provided"}), 400
    video = request.files['video']
    title = request.form.get('title', 'Untitled')
    if video.filename == '':
        return jsonify({"error": "No selected file"}), 400
    file_extension = os.path.splitext(video.filename)[1]
    safe_title = title.replace(" ", "_")
    filename = f"{safe_title}{file_extension}"
    preview_filename = f"{safe_title}.png"
    preview_path = os.path.join(URLP_FOLDER, preview_filename)
    video_path = os.path.join(URL_FOLDER, filename)
    video.save(video_path)
    video_url = f"/get_video|{safe_title}"
    preview_url = f"/get_preview|{safe_title}"
    try:
        clip = VideoFileClip(video_path)
        clip.save_frame(preview_path, t=5)
        clip.close()
    except Exception as e:
        return jsonify({"error": f"Error processing video: {str(e)}"}), 500
    new_video = Video(user_id=user_id, title=title, url=video_url, preview=preview_url)
    db.session.add(new_video)
    db.session.commit()
    return jsonify({"id": new_video.id, "title": new_video.title, "url": new_video.url}), 201

@app.route('/api/videos', methods=['GET'])
def get_videos2():
    videos = Video.query.all()
    data = []
    for video in videos:
        comments = Comment.query.filter_by(video_id=video.id).all()
        creator = video.creator
        data.append({
            "id": video.id,
            "title": video.title,
            "description": video.description,
            "url": video.url,
            "preview": video.preview,
            "creator": {
                "id": creator.id,
                "username": creator.username,
                "email": creator.email
            } if creator else None,
            "comments": [
                {
                    "id": comment.id,
                    "user_id": comment.userid,
                    "username": comment.username,
                    "text": comment.text
                }
                for comment in comments
            ]
        })
    return jsonify(data)

@app.route('/api/videos/<int:video_id>', methods=['DELETE'])
@jwt_required()
def delete_video(video_id):
    video = Video.query.get(video_id)
    if not video:
        return jsonify({"error": "Видео не найдено"}), 404
    try:
        db.session.delete(video)
        db.session.commit()
        return jsonify({"success": True, "message": "Видео успешно удалено"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": "Ошибка при удалении видео", "details": str(e)}), 500

@app.route('/add_comment', methods=['POST'])
@jwt_required()
def add_comment():
    try:
        comment = request.get_json()
        if not comment:
            return jsonify({"error": "Нет данных для комментария"}), 400
        current_user = get_jwt()
        current_user_id = get_jwt_identity()
        username = current_user.get("username")
        userid = current_user_id
        video_id = comment.get("video_id")
        text = comment.get("text")
        if video_id is None or text is None:
            return jsonify({"error": "Не хватает данных"}), 400
        new_comment = Comment(userid=userid, username=username, video_id=video_id, text=text)
        db.session.add(new_comment)
        db.session.commit()
        return jsonify({"success": True}), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/get_user', methods=['GET'])
@jwt_required()
def get_user():
    try:
        current_user = get_jwt()
        return jsonify(current_user), 200
    except Exception as ex:
        return jsonify({"error": str(ex)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
