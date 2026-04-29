from flask import Flask, render_template, request, redirect, url_for, session, flash
from database import db, create_table
from werkzeug.security import generate_password_hash, check_password_hash
import os
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev_key")

create_table()

# ================= OTP =================
def generate_otp():
    return str(random.randint(100000, 999999))


def send_otp_email(receiver_email, otp):
    try:
        sender = os.getenv("EMAIL_USER")
        password = os.getenv("EMAIL_PASS")

        if not sender or not password:
            print("Email env missing")
            return False

        msg = MIMEMultipart()
        msg["From"] = sender
        msg["To"] = receiver_email
        msg["Subject"] = "OTP Verification"
        msg.attach(MIMEText(f"Your OTP is: {otp}", "plain"))

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(sender, password)
        server.sendmail(sender, receiver_email, msg.as_string())
        server.quit()

        return True

    except Exception as e:
        print("OTP ERROR:", e)
        return False


# ================= LOGIN =================
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        conn = db()
        cur = conn.cursor()
        cur.execute("SELECT username, email, password FROM users WHERE email=%s", (email,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user is not None and check_password_hash(user[2], password):
            session["user"] = user[0]
            return redirect("/main")

        flash("Invalid login")

    return render_template("login.html")


# ================= SIGNUP =================
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")

        otp = generate_otp()

        session["otp"] = otp
        session["temp_user"] = {
            "username": username,
            "email": email,
            "password": generate_password_hash(password)
        }

        if send_otp_email(email, otp):
            return redirect("/verify_otp")
        else:
            flash("OTP send failed")

    return render_template("signup.html")


# ================= VERIFY OTP =================
@app.route("/verify_otp", methods=["GET", "POST"])
def verify_otp():
    if request.method == "POST":
        user_otp = request.form.get("otp")

        if user_otp == session.get("otp"):
            user = session.get("temp_user")

            conn = db()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO users (username, email, password) VALUES (%s,%s,%s)",
                (user["username"], user["email"], user["password"])
            )
            conn.commit()
            cur.close()
            conn.close()

            session.pop("otp", None)
            session.pop("temp_user", None)

            flash("Signup successful")
            return redirect("/")

        flash("Invalid OTP")

    return render_template("otp.html")


# ================= MAIN =================
@app.route("/main")
def main():
    user = session.get("user")

    if not user:
        return redirect(url_for("login"))

    conn = db()
    cur = conn.cursor()

    cur.execute("""
        SELECT user_message, ai_message 
        FROM chat_history 
        WHERE username=%s
        ORDER BY id ASC
    """, (user,))

    chats = cur.fetchall() or []

    cur.close()
    conn.close()

    return render_template("main.html", username=user, chats=chats)


# ================= CHAT =================
@app.route("/ask", methods=["POST"])
def ask():
    user = session.get("user")
    if not user:
        return redirect("/")

    msg = request.form.get("message")

    if not msg:
        return redirect("/main")

    reply = "AI: " + msg[::-1]

    conn = db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO chat_history (username, user_message, ai_message) VALUES (%s,%s,%s)",
        (user, msg, reply)
    )
    conn.commit()
    cur.close()
    conn.close()

    return redirect("/main")


# ================= LOGOUT =================
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    app.run(host="0.0.0.0", port=port)