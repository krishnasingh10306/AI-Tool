from flask import Flask, render_template, request, redirect, url_for, session, flash
from database import db, create_table
import os
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev_key")

create_table()

# ---------------- LOGIN ----------------
@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = db()
        cur = conn.cursor()
        cur.execute("SELECT username, password FROM users WHERE email=%s", (email,))
        user = cur.fetchone()
        cur.close()
        conn.close()

        if user and check_password_hash(user[1], password):
            session["user"] = user[0]
            return redirect("/main")

        flash("Invalid login")

    return render_template("login.html")


# ---------------- SIGNUP ----------------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = generate_password_hash(request.form["password"])

        conn = db()
        cur = conn.cursor()

        cur.execute("INSERT INTO users (username, email, password) VALUES (%s,%s,%s)",
                    (username, email, password))

        conn.commit()
        cur.close()
        conn.close()

        return redirect("/")

    return render_template("signup.html")


# ---------------- MAIN ----------------
@app.route("/main")
def main():
    if "user" not in session:
        return redirect("/")

    conn = db()
    cur = conn.cursor()
    cur.execute("SELECT user_message, ai_message FROM chat_history WHERE username=%s",
                (session["user"],))
    chats = cur.fetchall()
    cur.close()
    conn.close()

    return render_template("main.html", user=session["user"], chats=chats)


# ---------------- CHAT ----------------
@app.route("/ask", methods=["POST"])
def ask():
    if "user" not in session:
        return redirect("/")

    msg = request.form["message"]

    reply = "AI Response: " + msg[::-1]  # demo AI (replace with Gemini later)

    conn = db()
    cur = conn.cursor()
    cur.execute("INSERT INTO chat_history (username, user_message, ai_message) VALUES (%s,%s,%s)",
                (session["user"], msg, reply))
    conn.commit()
    cur.close()
    conn.close()

    return redirect("/main")


# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


if __name__ == "__main__":
    app.run(debug=True)