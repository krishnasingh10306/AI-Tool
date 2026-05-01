from flask import Flask, render_template, request, redirect, url_for, session, flash
from database import db, create_table
from validation import password_validation, valid_email

import random
import smtplib
import os
import time

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from google import genai
from diffusers import StableDiffusionPipeline
import torch
from huggingface_hub import login


app = Flask(__name__)
app.secret_key = "9315"

create_table()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
EMAIL_PASS = os.getenv("EMAIL_PASS")
HF_TOKEN = os.getenv("HF_TOKEN")


client = None
try:
    if GEMINI_API_KEY:
        client = genai.Client(api_key=GEMINI_API_KEY)
        print("Gemini client loaded successfully.")
    else:
        print("GEMINI_API_KEY not found. Text generation will not work.")
except Exception as e:
    print("Gemini setup error:", e)
    client = None


image_pipe = None
try:
    if HF_TOKEN:
        login(token=HF_TOKEN)

        image_pipe = StableDiffusionPipeline.from_pretrained(
            "sd-legacy/stable-diffusion-v1-5",
            torch_dtype=torch.float32
        )

        image_pipe = image_pipe.to("cpu")
        image_pipe.enable_attention_slicing()

        print("Stable Diffusion model loaded successfully.")
    else:
        print("HF_TOKEN not found. Image generation will not work.")
except Exception as e:
    print("Image model loading error:", e)
    image_pipe = None


def generate_otp():
    return str(random.randint(100000, 999999))


def send_otp_email(receiver_email, otp):
    try:
        sender_email = "krishnasingh10306@gmail.com"
        sender_password = EMAIL_PASS

        if not sender_password:
            print("EMAIL_PASS not found.")
            return False

        msg = MIMEMultipart()
        msg["From"] = sender_email
        msg["To"] = receiver_email
        msg["Subject"] = "OTP Verification"
        msg.attach(MIMEText(f"Your OTP is: {otp}", "plain"))

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, receiver_email, msg.as_string())
        server.quit()

        return True

    except Exception as e:
        print("Email sending error:", e)
        return False


def generate_text(prompt):
    try:
        if client is None:
            return "Error: GEMINI_API_KEY not found or Gemini client failed to load."

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt
        )

        if response.text:
            return response.text.strip()

        return "No response generated."

    except Exception as e:
        print("Text generation error:", e)
        return f"Error: {e}"


def is_image_prompt(prompt):
    prompt = prompt.lower()

    image_words = [
        "generate image",
        "create image",
        "make image",
        "draw",
        "photo",
        "picture",
        "portrait",
        "art",
        "illustration",
        "wallpaper",
        "logo",
        "poster",
        "thumbnail",
        "image of"
    ]

    return any(word in prompt for word in image_words)


def clean_image_prompt(prompt):
    prompt = prompt.lower()

    remove_words = [
        "generate image of",
        "create image of",
        "make image of",
        "generate image",
        "create image",
        "make image",
        "image of",
        "photo of",
        "picture of",
        "draw"
    ]

    for word in remove_words:
        prompt = prompt.replace(word, "")

    return prompt.strip()


def generate_image(prompt):
    try:
        if image_pipe is None:
            return None, "Image model is not loaded. Please set HF_TOKEN correctly."

        output_folder = os.path.join("static", "generated")
        os.makedirs(output_folder, exist_ok=True)

        final_prompt = clean_image_prompt(prompt)

        if not final_prompt:
            return None, "Please enter a proper image prompt."

        if len(final_prompt) < 3:
            return None, "Image prompt is too short."

        if len(final_prompt) > 300:
            return None, "Image prompt is too long."

        result = image_pipe(
            final_prompt,
            num_inference_steps=20,
            height=512,
            width=512
        )

        image = result.images[0]

        filename = f"generated/img_{int(time.time())}.png"
        full_path = os.path.join("static", filename)

        image.save(full_path)

        return filename, None

    except Exception as e:
        print("Image generation error:", e)
        return None, f"Error: {e}"


@app.route("/")
def home():
    return redirect(url_for("login_page"))


@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        conn = db()
        user = conn.execute(
            "SELECT * FROM users WHERE email = ? AND password = ?",
            (email, password)
        ).fetchone()
        conn.close()

        if user:
            session["user"] = user["username"]
            session["email"] = user["email"]

            if "chat_history" not in session:
                session["chat_history"] = []

            flash("Login successful", "success")
            return redirect(url_for("main"))

        flash("Invalid email or password", "error")

    return render_template("login.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        fullname = request.form.get("fullname", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()

        if not fullname:
            flash("Full name is required", "error")
            return render_template("signup.html")

        if not valid_email(email):
            flash("Invalid email format", "error")
            return render_template("signup.html")

        if not password_validation(password):
            flash(
                "Password must contain uppercase, lowercase, digit, special character and minimum 8 characters",
                "error"
            )
            return render_template("signup.html")

        if password != confirm_password:
            flash("Password and Confirm Password do not match", "error")
            return render_template("signup.html")

        conn = db()
        existing_user = conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        ).fetchone()
        conn.close()

        if existing_user:
            flash("Email already exists", "error")
            return render_template("signup.html")

        otp = generate_otp()

        session["signup_name"] = fullname
        session["signup_email"] = email
        session["signup_password"] = password
        session["signup_otp"] = otp

        if send_otp_email(email, otp):
            flash("OTP sent to your email", "success")
            return redirect(url_for("verify_otp"))

        flash("Could not send OTP email", "error")
        return render_template("signup.html")

    return render_template("signup.html")


@app.route("/verify_otp", methods=["GET", "POST"])
def verify_otp():
    if request.method == "POST":
        user_otp = request.form.get("otp", "").strip()
        saved_otp = session.get("signup_otp")

        if not saved_otp:
            flash("OTP expired. Please sign up again.", "error")
            return redirect(url_for("signup"))

        if user_otp == saved_otp:
            fullname = session.get("signup_name")
            email = session.get("signup_email")
            password = session.get("signup_password")

            conn = db()
            conn.execute(
                "INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
                (fullname, email, password)
            )
            conn.commit()
            conn.close()

            session.pop("signup_name", None)
            session.pop("signup_email", None)
            session.pop("signup_password", None)
            session.pop("signup_otp", None)

            flash("Signup successful. Please login now.", "success")
            return redirect(url_for("login_page"))

        flash("Invalid OTP", "error")

    return render_template("verify_otp.html")


@app.route("/forgot_password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form.get("email", "").strip()

        conn = db()
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        ).fetchone()
        conn.close()

        if not user:
            flash("Email not found", "error")
            return render_template("forgot_password.html")

        otp = generate_otp()

        session["reset_email"] = email
        session["reset_otp"] = otp
        session["reset_verified"] = False

        if send_otp_email(email, otp):
            flash("OTP sent to your email", "success")
            return redirect(url_for("reset_otp"))

        flash("Could not send OTP email", "error")
        return render_template("forgot_password.html")

    return render_template("forgot_password.html")


@app.route("/reset_otp", methods=["GET", "POST"])
def reset_otp():
    if request.method == "POST":
        user_otp = request.form.get("otp", "").strip()
        saved_otp = session.get("reset_otp")

        if not saved_otp:
            flash("OTP expired. Try again.", "error")
            return redirect(url_for("forgot_password"))

        if user_otp == saved_otp:
            session["reset_verified"] = True
            flash("OTP verified successfully", "success")
            return redirect(url_for("reset_password"))

        flash("Invalid OTP", "error")

    return render_template("reset_otp.html")


@app.route("/reset_password", methods=["GET", "POST"])
def reset_password():
    if not session.get("reset_verified"):
        flash("Please verify OTP first", "error")
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        new_password = request.form.get("new_password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()

        if new_password != confirm_password:
            flash("Password and Confirm Password do not match", "error")
            return render_template("reset_password.html")

        if not password_validation(new_password):
            flash(
                "Password must contain uppercase, lowercase, digit, special character and minimum 8 characters",
                "error"
            )
            return render_template("reset_password.html")

        conn = db()
        conn.execute(
            "UPDATE users SET password = ? WHERE email = ?",
            (new_password, session.get("reset_email"))
        )
        conn.commit()
        conn.close()

        session.pop("reset_email", None)
        session.pop("reset_otp", None)
        session.pop("reset_verified", None)

        flash("Password updated successfully. Please login.", "success")
        return redirect(url_for("login_page"))

    return render_template("reset_password.html")


@app.route("/main", methods=["GET", "POST"])
@app.route("/gpt", methods=["GET", "POST"])
def main():
    if "user" not in session:
        flash("Please login first", "error")
        return redirect(url_for("login_page"))

    if "chat_history" not in session:
        session["chat_history"] = []

    quick_prompt = request.form.get("quick_prompt")

    return render_template(
        "gpt.html",
        username=session.get("user"),
        chats=session.get("chat_history"),
        search_keyword=None,
        quick_prompt=quick_prompt,
        current_user_message=None,
        current_ai_message=None,
        image_file=None
    )


@app.route("/ask_ai", methods=["POST"])
def ask_ai():
    if "user" not in session:
        flash("Please login first", "error")
        return redirect(url_for("login_page"))

    if "chat_history" not in session:
        session["chat_history"] = []

    prompt = request.form.get("prompt", "").strip()

    if not prompt:
        flash("Please enter a prompt", "error")
        return redirect(url_for("main"))

    image_file = None

    if is_image_prompt(prompt):
        image_file, error = generate_image(prompt)
        ai_response = error if error else "Image generated successfully."
    else:
        ai_response = generate_text(prompt)

    chat_id = len(session["chat_history"]) + 1

    new_chat = {
        "id": chat_id,
        "user_message": prompt,
        "ai_message": ai_response,
        "image_file": image_file
    }

    session["chat_history"].append(new_chat)
    session.modified = True

    return render_template(
        "gpt.html",
        username=session.get("user"),
        chats=session.get("chat_history"),
        current_user_message=prompt,
        current_ai_message=ai_response,
        image_file=image_file,
        search_keyword=None,
        quick_prompt=None
    )


@app.route("/search_chats", methods=["POST"])
def search_chats():
    if "user" not in session:
        flash("Please login first", "error")
        return redirect(url_for("login_page"))

    keyword = request.form.get("keyword", "").strip()
    chats = session.get("chat_history", [])

    filtered_chats = []

    if keyword:
        for chat in chats:
            if keyword.lower() in chat.get("user_message", "").lower():
                filtered_chats.append(chat)

    return render_template(
        "gpt.html",
        username=session.get("user"),
        chats=filtered_chats,
        search_keyword=keyword,
        quick_prompt=None,
        current_user_message=None,
        current_ai_message=None,
        image_file=None
    )


@app.route("/open_chat/<int:chat_id>")
def open_chat(chat_id):
    if "user" not in session:
        flash("Please login first", "error")
        return redirect(url_for("login_page"))

    chats = session.get("chat_history", [])

    selected_chat = None

    for chat in chats:
        if chat.get("id") == chat_id:
            selected_chat = chat
            break

    if not selected_chat:
        flash("Chat not found", "error")
        return redirect(url_for("main"))

    return render_template(
        "gpt.html",
        username=session.get("user"),
        chats=chats,
        current_user_message=selected_chat.get("user_message"),
        current_ai_message=selected_chat.get("ai_message"),
        image_file=selected_chat.get("image_file"),
        search_keyword=None,
        quick_prompt=None
    )


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully", "success")
    return redirect(url_for("login_page"))


if __name__ == "__main__":
    app.run(debug=True)