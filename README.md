# 🧹 Chores App with SMS and Web Interface

This is a full-featured Flask-based Chores App that supports two-way SMS communication using Twilio. It allows assigning, completing, and listing chores via text message or through a web interface. The app supports recurring chores, admin notifications, daily reminders, and conversation state management.

---

## 🚀 Features

- 📱 **Two-way SMS Integration** using Twilio
- ✅ **Mark chores as done** via SMS (`DONE chore name`)
- 📋 **List chores** via SMS (`LIST`)
- ➕ **Add chores via natural SMS** (`Add laundry to Erica due tomorrow every week`)
- 🔁 **Support for recurring chores** (daily, weekly, monthly, every X days/weeks/months)
- 🔔 **Daily chore reminders via SMS** at 8 AM
- 🛂 **Admin notifications** when chores are completed
- 🧠 **Conversation state tracking** for multi-step SMS interactions
- 🌐 **Web UI** to view, assign, complete, and filter chores
- 🗃️ **Chore history** page with filters
- 🧼 **Automatic cleanup** of old conversation states

---

## 🧱 Tech Stack

- **Python 3.9+**
- **Flask** for the web server
- **SQLAlchemy** + **SQLite** for the database
- **Twilio** for SMS messaging
- **Dateparser** for natural language date recognition
- **Schedule** + **Threading** for background SMS reminders
- **Bootstrap (optional)** for styling the web UI