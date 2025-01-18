from flask import Flask, request, jsonify, render_template
import mysql.connector
from datetime import datetime, timezone
import base64
import os

app = Flask(__name__)

# Database connection function
def get_db_connection():
    try:
        print("Attempting database connection...")
        return mysql.connector.connect(
            host='192.168.0.105',
            user='storeUser',
            password='TkDb#121',
            database='task_management'
        )
    except mysql.connector.Error as e:
        print(f"Database connection failed: {e}")
        raise

@app.route("/")
def home():
    return render_template("login.html")

@app.route("/login", methods=["POST"])
def login():
    try:
        # Parse JSON data from the request
        data = request.get_json()
        username = data.get("username")
        password = data.get("password")
    except Exception as e:
        return jsonify({"message": "Invalid request format."}), 400

    if not username or not password:
        return jsonify({"message": "Please provide both username and password."}), 400

    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT storeUser, storePass, storeID FROM stores WHERE storeUser = %s", (username,))
        user = cursor.fetchone()
        cursor.close()
        db.close()

        if user and user["storePass"] == password:
            # If login is successful, return storeID along with the redirect URL
            store_id = user["storeID"]
            if username == "admin":
                return jsonify({"message": "Login successful!", "redirect_url": "/hq_dashboard", "store_id": store_id}), 200
            else:
                return jsonify({"message": "Login successful!", "redirect_url": "/store_dashboard?storeID="+store_id}), 200
        else:
            return jsonify({"message": "Invalid username or password!"}), 401

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"message": "An error occurred while processing your request."}), 500
    

@app.route('/add_task', methods=['POST'])
def create_task():
    try:
        # Parse JSON data from the request
        data = request.json
        title = data.get('name')  # Mapping 'name' from front-end to 'title' in DB
        description = data.get('description')
        priority = data.get('priority')
        attachment_required = data.get('attachmentRequired', False)
        due_date = data.get('dueDate')
        due_time = data.get('dueTime')
        store_ids = ','.join(data.get('stores', []))  # Combine store IDs as a comma-separated string

        # Validate required fields
        if not title or not description or not due_date or not priority:
            return jsonify({"success": False, "message": "Missing required fields"}), 400

        # Validate priority values
        if priority not in ['1', '2', '3']:
            return jsonify({"success": False, "message": "Invalid priority level"}), 400

        # Combine due_date and due_time into a single datetime string
        full_due_date = f"{due_date} {due_time}"

        # Insert task into the database
        try:
            connection = get_db_connection()
            cursor = connection.cursor()
            query = """
                INSERT INTO tasks (title, description, priority, due_date, attachments, store_ids, status, created_at, created_by)
                VALUES (%s, %s, %s, %s, %s, %s, 'pending', CURRENT_TIMESTAMP, 'ADMIN')
            """
            values = (title, description, priority, full_due_date, int(attachment_required), store_ids)
            cursor.execute(query, values)
            connection.commit()
        finally:
            # Close resources in the finally block to avoid leaks
            if cursor:
                cursor.close()
            if connection:
                connection.close()

        return jsonify({"success": True, "message": "Task created successfully"}), 201

    except mysql.connector.Error as e:
        print(f"Database error: {e}")
        return jsonify({"success": False, "message": "Database error occurred"}), 500
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"success": False, "message": "An error occurred"}), 500

from flask import Flask, render_template, redirect, url_for, session

@app.route("/hq_dashboard", methods=["GET", "POST"])
def hq_dashboard():
    sort_by = request.args.get('sort_by', 'priority_desc')  # Default sorting by priority (high to low)

    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)
        
        # Adjust SQL query based on the sort order
        if sort_by == 'priority_desc':
            cursor.execute("SELECT id, title, description, priority, due_date, store_ids, store_ids_completed FROM tasks ORDER BY priority DESC, due_date ASC")
        elif sort_by == 'priority_asc':
            cursor.execute("SELECT id, title, description, priority, due_date, store_ids, store_ids_completed FROM tasks ORDER BY priority ASC, due_date ASC")
        elif sort_by == 'due_date_asc':
            cursor.execute("SELECT id, title, description, priority, due_date, store_ids, store_ids_completed FROM tasks ORDER BY due_date ASC, priority DESC")
        elif sort_by == 'due_date_desc':
            cursor.execute("SELECT id, title, description, priority, due_date, store_ids, store_ids_completed FROM tasks ORDER BY due_date DESC, priority DESC")
        else:
            cursor.execute("SELECT id, title, description, priority, due_date, store_ids, store_ids_completed FROM tasks ORDER BY priority DESC, due_date ASC")
        
        tasks = cursor.fetchall()

        # Process tasks to calculate completed stores and convert priority
        for task in tasks:
            total_stores = len(task["store_ids"].split(",")) if task["store_ids"] else 0
            completed_stores = len(task["store_ids_completed"].split(",")) if task["store_ids_completed"] else 0
            task["completion"] = f"{completed_stores}/{total_stores}"  # Add a new field to the task dict
            
            # Convert priority to label and color
            priority_map = {
                '1': {'label': 'Low', 'color': 'green'},
                '2': {'label': 'Medium', 'color': 'yellow'},
                '3': {'label': 'High', 'color': 'red'}
            }
            priority_data = priority_map.get(str(task["priority"]), {'label': 'Unknown', 'color': 'gray'})
            task["priority_label"] = priority_data["label"]
            task["priority_color"] = priority_data["color"]

        cursor.close()
        db.close()

        return render_template("hq_dashboard.html", tasks=tasks, sort_by=sort_by)

    except mysql.connector.Error as e:
        print(f"Database error: {e}")
        return jsonify({"message": "Database error"}), 500
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"message": "An error occurred"}), 500

    

@app.route('/task/<int:task_id>')
def task_details(task_id):
    try:
        # Connect to DB
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        # Fetch task details
        cursor.execute("SELECT id, title, description, priority, created_at, due_date, store_ids, store_ids_completed, attachments FROM tasks WHERE id = %s", (task_id,))
        task = cursor.fetchone()

        if not task:
            return jsonify({"message": "Task not found!"}), 404
        
        # Fetch associated stores (store_id must match with store_ids in the task)
        store_ids = task["store_ids"].split(",")  # Assuming store_ids are stored as comma-separated values
        
        if store_ids:
            # Create placeholders for the SQL query based on the number of store IDs
            placeholders = ', '.join(['%s'] * len(store_ids))
            cursor.execute(f"SELECT idstores, storeID, storeName, storeUser, storePass FROM stores WHERE storeID IN ({placeholders})", tuple(store_ids))
            stores = cursor.fetchall()
        else:
            stores = []  # No stores associated with the task

        # Get completed store IDs (those that are marked as completed in task)
        completed_store_ids = task["store_ids_completed"].split(",") if task["store_ids_completed"] else []

        # Mark each store as completed or not based on the store_id
        for store in stores:
            store["completed"] = store["storeID"] in completed_store_ids
            if store["completed"]:
                # Calculate time taken to complete the task
                try:
                    cursor.execute(
                                "SELECT date_completed FROM task_log WHERE storeID = %s AND taskID = %s", 
                                (store['storeID'], task_id)
                    )
                    datecomp = cursor.fetchone()

                    due_date = task['due_date']
                    assigned_date = task['created_at'] if isinstance(task['created_at'], datetime) else datetime.strptime(task['created_at'], "%Y-%m-%d %H:%M:%S")
                    completed_date = datecomp['date_completed'] if isinstance(datecomp['date_completed'], datetime) else datetime.strptime(datecomp['date_completed'], "%Y-%m-%d %H:%M:%S")

                    time_diff = completed_date - assigned_date
                    days = time_diff.days
                    hours = time_diff.seconds // 3600

                    store["time_taken"] = f"{days} days {hours} hours"
                    store["completed_date"] = datecomp['date_completed']
                    store["overdue"] = completed_date > due_date
                except Exception as e:
                    print(f"Error calculating time taken: {e}")
                    store["time_taken"] = "Unknown"
                    store["overdue"] = False  # Default to not overdue
            else:
                store["time_taken"] = "Not Completed"
                store["overdue"] = False  # Default to not overdue

        import base64

        for store in stores:
            try:
                # Fetch attachment for the store
                cursor.execute(
                    "SELECT attachment FROM task_log WHERE storeID = %s AND taskID = %s", 
                    (store['storeID'], task_id)
                )
                attachment = cursor.fetchone()

                # If an attachment exists, convert it to base64
                if attachment and attachment['attachment']:
                    attachment_blob = attachment['attachment']
                    attachment_base64 = base64.b64encode(attachment_blob).decode('utf-8')
                    store["attachment_base64"] = attachment_base64
                else:
                    store["attachment_base64"] = None  # No attachment

            except mysql.connector.Error as e:
                print(f"Database error while fetching attachment for store {store['storeID']}: {e}")
                store["attachment_base64"] = None  # Handle error gracefully

        # Process task completion
        total_stores = len(store_ids)
        completed_stores = len(completed_store_ids)
        task["completion"] = f"{completed_stores}/{total_stores}"
        task["attachment_required"] = task['attachments']

        # Convert priority to label and color
        priority_map = {
            '1': {'label': 'Low', 'color': 'green'},
            '2': {'label': 'Medium', 'color': 'yellow'},
            '3': {'label': 'High', 'color': 'red'}
        }
        priority_data = priority_map.get(str(task["priority"]), {'label': 'Unknown', 'color': 'gray'})
        task["priority_label"] = priority_data["label"]
        task["priority_color"] = priority_data["color"]

        cursor.close()
        db.close()

        # Pass data to template
        return render_template("task_details.html", task=task, stores=stores)

    except mysql.connector.Error as e:
        print(f"Database error: {e}")
        return jsonify({"message": "Database error"}), 500
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"message": "An error occurred"}), 500

@app.route('/task/<int:task_id>/delete', methods=['POST'])
def delete_task(task_id):
    try:
        # Connect to DB
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        # Delete task from the database
        cursor.execute("DELETE FROM tasks WHERE id = %s", (task_id,))
        db.commit()

        # Close connection
        cursor.close()
        db.close()

        # Redirect or return success message
        return redirect('/hq_dashboard')  # Redirect to the dashboard after deletion

    except mysql.connector.Error as e:
        print(f"Database error: {e}")
        return jsonify({"message": "Database error"}), 500
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"message": "An error occurred"}), 500
    
from flask import request

@app.route("/store_dashboard", methods=["GET"])
def store_dashboard():
    storeID = request.args.get("storeID")
    sort_by = request.args.get("sort_by", "priority_desc")  # Default sorting by priority (High to Low)

    if not storeID or storeID == '0':
        return jsonify({"message": "Store ID is required."}), 400

    try:
        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        # Query for incomplete tasks
        cursor.execute("""
            SELECT id, title, description, due_date, store_ids, priority
            FROM tasks 
            WHERE (NOT FIND_IN_SET(%s, store_ids_completed) > 0 OR store_ids_completed IS NULL) 
              AND FIND_IN_SET(%s, store_ids) > 0
        """, (storeID, storeID))
        tasks_incomplete = cursor.fetchall()

        # Query for completed tasks (no sorting needed here)
        cursor.execute("""
            SELECT tasks.id, tasks.priority, tasks.title, tasks.description, tasks.due_date, task_log.date_completed
            FROM tasks
            JOIN task_log ON tasks.id = task_log.taskID
            WHERE FIND_IN_SET(%s, tasks.store_ids) > 0 AND FIND_IN_SET(%s, tasks.store_ids_completed) > 0 AND FIND_IN_SET(%s, task_log.storeID) > 0
        """, (storeID, storeID, storeID))
        tasks_completed = cursor.fetchall()

        # Sorting logic for incomplete tasks
        if sort_by == 'priority_desc':
            tasks_incomplete.sort(key=lambda x: (x["priority"], x["due_date"]), reverse=True)
        elif sort_by == 'priority_asc':
            tasks_incomplete.sort(key=lambda x: (x["priority"], x["due_date"]))
        elif sort_by == 'due_date_asc':
            tasks_incomplete.sort(key=lambda x: (x["due_date"], x["priority"]))
        elif sort_by == 'due_date_desc':
            tasks_incomplete.sort(key=lambda x: (x["due_date"], x["priority"]), reverse=True)

        # Enhance task data with priority label and color
        priority_map = {
            '1': {'label': 'Low', 'color': 'green'},
            '2': {'label': 'Medium', 'color': 'yellow'},
            '3': {'label': 'High', 'color': 'red'}
        }

        for task in tasks_incomplete:
            priority = str(task["priority"]) if task.get("priority") is not None else '0'
            priority_data = priority_map.get(priority, {'label': 'Unknown', 'color': 'gray'})
            task["priority_label"] = priority_data["label"]
            task["priority_color"] = priority_data["color"]

        cursor.close()
        db.close()

        # Render the HTML template and pass the tasks
        return render_template("store_dashboard.html", tasks_incomplete=tasks_incomplete, tasks_completed=tasks_completed, storeID=storeID, sort_by=sort_by)

    except mysql.connector.Error as e:
        print(f"Database error: {e}")
        return jsonify({"message": "Database error"}), 500
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"message": "An error occurred"}), 500


@app.route('/task_store_details')
def task_store_details():
    try:
        store_id = request.args.get('storeID')
        task_id = request.args.get('taskID')

        if not store_id or not task_id:
            return jsonify({"message": "Missing storeID or taskID in the request"}), 400

        db = get_db_connection()
        cursor = db.cursor(dictionary=True)

        # Fetch task details from the database
        cursor.execute("SELECT id, title, description, priority, due_date, store_ids, store_ids_completed, attachments FROM tasks WHERE id = %s", (task_id,))
        task = cursor.fetchone()

        if not task:
            return jsonify({"message": "Task not found!"}), 404

        # Verify if task is assigned to the store
        store_ids = task["store_ids"].split(",") if task["store_ids"] else []
        if store_id not in store_ids:
            return jsonify({"message": "Task not assigned to this store"}), 403

        # Check if task is completed for this store
        completed_store_ids = task["store_ids_completed"].split(",") if task["store_ids_completed"] else []
        task_completed = store_id in completed_store_ids

        # Map priority
        priority_map = {
            '1': {'label': 'Low', 'color': 'green'},
            '2': {'label': 'Medium', 'color': 'yellow'},
            '3': {'label': 'High', 'color': 'red'}
        }
        priority_data = priority_map.get(str(task["priority"]), {'label': 'Unknown', 'color': 'gray'})
        task["priority_label"] = priority_data["label"]
        task["priority_color"] = priority_data["color"]

        # Check if attachment is required
        task["attachment_required"] = bool(task["attachments"])

        cursor.close()
        db.close()

        return render_template("task_store_details.html", task=task, task_completed=task_completed)

    except mysql.connector.Error as e:
        print(f"Database error: {e}")
        return jsonify({"message": "Database error"}), 500
    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"message": "An error occurred"}), 500

@app.route('/add_attachment', methods=['POST'])
def add_attachment():
    try:
        store_id = request.form.get('storeID')
        task_id = request.form.get('taskID')
        attachment = request.files.get('attachment')

        if not store_id or not task_id or not attachment:
            return jsonify({"message": "Missing required fields"}), 400

        allowed_extensions = {'jpg', 'jpeg', 'png', 'gif'}
        filename = attachment.filename

        if '.' not in filename or filename.rsplit('.', 1)[1].lower() not in allowed_extensions:
            return jsonify({"message": "Invalid file type"}), 400

        attachment_data = attachment.read()
        encoded_image = base64.b64encode(attachment_data).decode('utf-8')

        return jsonify({"message": "Attachment uploaded successfully", "attachment_preview": encoded_image}), 200
    except Exception as e:
        print(f"Error uploading attachment: {e}")
        return jsonify({"message": "An error occurred while uploading the attachment"}), 500

@app.route('/complete_task', methods=['POST'])
def complete_task():
    cursor = None  # Initialize cursor to None
    db = None  # Initialize db to None for safety
    try:
        store_id = request.form.get('storeID')
        task_id = request.form.get('taskID')
        attachment_data = request.form.get('attachment')  # Base64 encoded attachment

        if not store_id or not task_id:
            return jsonify({"message": "Missing required fields"}), 400

        decoded_attachment = base64.b64decode(attachment_data) if attachment_data else None

        from pytz import timezone

        # Get South Africa timezone (UTC+2)
        south_africa = timezone('Africa/Johannesburg')
        current_time_utc = datetime.now(south_africa)

        db = get_db_connection()  # Connect to the database
        cursor = db.cursor()

        # Insert into task_log table
        cursor.execute("""
            INSERT INTO task_log (storeID, taskID, date_completed, attachment)
            VALUES (%s, %s, %s, %s)
        """, (store_id, task_id, current_time_utc, decoded_attachment))
        db.commit()

        # Update tasks table (if necessary)
        cursor.execute("""
            UPDATE tasks
            SET store_ids_completed = 
                CASE 
                    WHEN store_ids_completed IS NULL THEN %s 
                    ELSE CONCAT(store_ids_completed, ',', %s)
                END
            WHERE id = %s
        """, (store_id, store_id, task_id))
        db.commit()

        return jsonify({"success": True, "message": "Task completed successfully"}), 200

    except mysql.connector.Error as e:
        print(f"Database error: {e}")
        return jsonify({"message": f"Database error: {e}"}), 500
    except Exception as e:
        print(f"Error completing task: {e}")
        return jsonify({"message": f"An error occurred: {e}"}), 500
    finally:
        # Close cursor and db connection
        if cursor:
            cursor.close()
        if db:
            db.close()


@app.route("/task_creator")
def task_creator():
    return render_template("task_creator.html")

@app.route("/logout")
def logout():
    session.clear()
    return jsonify({"message": "Logged out successfully!", "redirect_url": "/login"}), 200

if __name__ == "__main__":
    get_db_connection()
    app.run(debug=True)
