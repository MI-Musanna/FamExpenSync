from flask import Flask, render_template, request, redirect, url_for, Response, flash, session, jsonify
import models
import database
from config import SECRET_KEY
import csv
import io
import logging

app = Flask(__name__)
app.secret_key = SECRET_KEY

logging.basicConfig(
    filename='error.log',
    level=logging.ERROR,
    format='%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
)

@app.teardown_appcontext
def shutdown_session(exception=None):
    database.db_session.remove()

@app.errorhandler(500)
def internal_server_error(e):
    logging.error(f"Global 500 Triggered: {str(e)}", exc_info=True)
    return "Internal Server Error (500). Please check your error.log file or reset the database.", 500

@app.route('/verify_pin', methods=['POST'])
def verify_pin():
    try:
        member_id = request.form.get('member_id')
        input_pin = request.form.get('pin', '').strip()
        
        member_obj = database.db_session.get(models.Member, int(member_id))
        if member_obj and member_obj.pin == input_pin:
            session[f'auth_member_{member_id}'] = True
            return jsonify({"status": "success"}), 200
            
        return jsonify({"status": "error", "message": "Invalid Security PIN!"}), 401
    except Exception as e:
        logging.error("PIN Verification Route Exception thrown", exc_info=True)
        return jsonify({"status": "error", "message": "Authentication Subsystem Failure"}), 500

@app.route('/')
def index():
    try:
        models.check_and_generate_recurring_expenses()

        members = models.get_all_members()
        member_filter = request.args.get('member_filter', 'all')
        time_filter = request.args.get('time_filter', 'all')
        search_query = request.args.get('search', '').strip()
        edit_id = request.args.get('edit_id')
        
        if member_filter != 'all':
            session_key = f'auth_member_{member_filter}'
            if session.get(session_key) is not True:
                flash("Access Denied: Please select and authenticate the profile correctly! 🔐", "error")
                return redirect(url_for('index', member_filter='all', time_filter=time_filter, search=search_query))

        form_member_id = 1 if member_filter == 'all' else int(member_filter)
        categories = models.get_categories_by_member(form_member_id)
        recurring_templates = models.get_recurring_templates_by_member(form_member_id)
        
        edit_expense = database.db_session.get(models.Expense, int(edit_id)) if edit_id else None
        expenses = models.get_filtered_expenses(member_filter, time_filter, search_query)
        total_expense = sum(row.amount for row in expenses)
        budget = models.get_budget()
        
        chart_data = {}
        for row in expenses:
            cat = row.category.name
            chart_data[cat] = chart_data.get(cat, 0) + row.amount
        
        all_expenses = database.db_session.query(models.Expense).all()
        trend_map = {}
        for exp in all_expenses:
            m_key = exp.date[:7] if len(exp.date) >= 7 else "Unknown"
            trend_map[m_key] = trend_map.get(m_key, 0) + exp.amount
            
        sorted_months = sorted(trend_map.keys())
        trend_values = [trend_map[m] for m in sorted_months]
        
        grouped_expenses = {}
        for row in expenses:
            cat_name = row.category.name
            if cat_name not in grouped_expenses:
                grouped_expenses[cat_name] = []
            grouped_expenses[cat_name].append(row)
            
        return render_template('index.html',
                               members=members,
                               categories=categories,
                               recurring_templates=recurring_templates,
                               grouped_expenses=grouped_expenses,
                               total_expense=total_expense,
                               current_member_filter=member_filter,
                               current_time_filter=time_filter,
                               current_search_query=search_query,
                               edit_expense=edit_expense,
                               form_member_id=form_member_id,
                               budget=budget,
                               chart_labels=list(chart_data.keys()),
                               chart_values=list(chart_data.values()),
                               trend_labels=sorted_months,
                               trend_values=trend_values)
    except Exception as e:
        logging.error("Exception occurred in index route", exc_info=True)
        raise e

@app.route('/add', methods=['POST'])
def add_expense():
    member_id = request.form['member_id']
    time_filter = request.form.get('current_time_filter', 'all')
    search_query = request.form.get('current_search_query', '')
    try:
        amount = float(request.form['amount'])
        category_id = int(request.form['category_id'])
        description = request.form['description'].strip()
        date = request.form['date'].strip()
        
        if amount <= 0:
            flash("Error: Amount must be greater than zero! ❌", "error")
        else:
            models.add_new_expense(member_id, category_id, amount, description, date)
            flash("Success: Transaction securely saved to core! 🎉", "success")
    except Exception as e:
        logging.error("Failed to append new expense row", exc_info=True)
        flash("Error: Invalid numeric formatting submitted! ❌", "error")
    return redirect(url_for('index', member_filter=member_id, time_filter=time_filter, search=search_query))

@app.route('/add_recurring', methods=['POST'])
def add_recurring():
    member_id = request.form['member_id'] if 'member_id' in request.form else request.form['form_member_id']
    time_filter = request.form.get('current_time_filter', 'all')
    search_query = request.form.get('current_search_query', '')
    try:
        amount = float(request.form['amount'])
        category_id = int(request.form['category_id'])
        description = request.form['description'].strip()
        models.add_recurring_template(int(member_id), category_id, amount, description)
        flash("Success: Fixed monthly bill template locked! ⏳", "success")
    except Exception as e:
        logging.error("Failed to append recurring template", exc_info=True)
        flash("Error: Failed to register fixed bill template! ❌", "error")
    return redirect(url_for('index', member_filter=member_id, time_filter=time_filter, search=search_query))

@app.route('/delete_recurring/<int:id>')
def delete_recurring(id):
    member_filter = request.args.get('member_filter', 'all')
    time_filter = request.args.get('time_filter', 'all')
    search_query = request.args.get('search', '')
    models.delete_recurring_template_by_id(id)
    flash("Success: Fixed bill template deleted! 🗑️", "success")
    return redirect(url_for('index', member_filter=member_filter, time_filter=time_filter, search=search_query))

@app.route('/update/<int:id>', methods=['POST'])
def update_expense(id):
    member_id = request.form['member_id']
    time_filter = request.form.get('current_time_filter', 'all')
    search_query = request.form.get('current_search_query', '')
    try:
        amount = float(request.form['amount'])
        category_id = int(request.form['category_id'])
        description = request.form['description'].strip()
        date = request.form['date'].strip()
        
        if amount <= 0:
            flash("Error: Inbound amount violation limit! ❌", "error")
        else:
            models.update_expense_by_id(id, member_id, category_id, amount, description, date)
            flash("Success: Database row sync complete! 📝", "success")
    except Exception as e:
        logging.error(f"Failed to modify expense row ID {id}", exc_info=True)
        flash("Error: Runtime verification failure! ❌", "error")
    return redirect(url_for('index', member_filter=member_id, time_filter=time_filter, search=search_query))

@app.route('/delete/<int:id>')
def delete_expense(id):
    member_filter = request.args.get('member_filter', 'all')
    time_filter = request.args.get('time_filter', 'all')
    search_query = request.args.get('search', '')
    try:
        models.delete_expense_by_id(id)
        flash("Success: Row purged from engine layer! 🗑️", "success")
    except Exception as e:
        logging.error(f"Error purging row ID {id}", exc_info=True)
    return redirect(url_for('index', member_filter=member_filter, time_filter=time_filter, search=search_query))

@app.route('/add_category', methods=['POST'])
def add_category():
    category_name = request.form['category_name'].strip()
    member_filter = request.form.get('current_member_filter', 'all')
    time_filter = request.form.get('current_time_filter', 'all')
    search_query = request.form.get('current_search_query', '')
    form_member_id = request.form.get('form_member_id')
    try:
        if category_name and form_member_id:
            models.add_new_category(category_name, int(form_member_id))
            flash(f"Success: Scoped category '{category_name}' appended! 🛠️", "success")
    except Exception as e:
        logging.error("Category insertion exception thrown", exc_info=True)
    return redirect(url_for('index', member_filter=member_filter, time_filter=time_filter, search=search_query))

@app.route('/delete_category/<int:id>')
def delete_category(id):
    member_filter = request.args.get('member_filter', 'all')
    time_filter = request.args.get('time_filter', 'all')
    search_query = request.args.get('search', '')
    try:
        models.delete_category_by_id(id)
        flash("Notification: Category task processed. Protected logs remain locked. ℹ️", "info")
    except Exception as e:
        logging.error(f"Failed to wipe category ID {id}", exc_info=True)
    return redirect(url_for('index', member_filter=member_filter, time_filter=time_filter, search=search_query))

@app.route('/update_budget', methods=['POST'])
def update_budget():
    new_budget = request.form['budget']
    member_filter = request.args.get('member_filter', 'all')
    time_filter = request.args.get('time_filter', 'all')
    search_query = request.args.get('search', '')
    try:
        if new_budget:
            models.update_budget(float(new_budget))
            flash("Success: Fiscal limitations updated! 🎯", "success")
    except Exception as e:
        logging.error("Budget recalibration engine error", exc_info=True)
    return redirect(url_for('index', member_filter=member_filter, time_filter=time_filter, search=search_query))

@app.route('/update_pin', methods=['POST'])
def update_pin():
    member_id = request.form['form_member_id']
    time_filter = request.form.get('current_time_filter', 'all')
    search_query = request.form.get('current_search_query', '')
    old_pin = request.form['old_pin'].strip()
    new_pin = request.form['new_pin'].strip()
    try:
        if models.update_member_pin(int(member_id), old_pin, new_pin):
            session[f'auth_member_{member_id}'] = True
            flash("Success: Profile Security PIN modified! 🔐", "success")
        else:
            flash("Error: Invalid credentials or PIN syntax failure! ❌", "error")
    except Exception as e:
        logging.error(f"PIN modification subsystem failure on user {member_id}", exc_info=True)
    return redirect(url_for('index', member_filter=member_id, time_filter=time_filter, search=search_query))

@app.route('/export')
def export_csv():
    member_filter = request.args.get('member_filter', 'all')
    time_filter = request.args.get('time_filter', 'all')
    search_query = request.args.get('search', '')
    try:
        expenses = models.get_filtered_expenses(member_filter, time_filter, search_query)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Date', 'Member', 'Category', 'Description', 'Amount'])
        for exp in expenses:
            writer.writerow([exp.date, exp.member.name, exp.category.name, exp.description, exp.amount])
        output.seek(0)
        return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename=family_expenses.csv"})
    except Exception as e:
        logging.error("CSV engine compiler failure", exc_info=True)
        return "Internal Compiler Error logged.", 500

if __name__ == '__main__':
    from waitress import serve
    database.init_db()
    print("------------------------------------------------------------------")
    print(" FamExpenSync Engine is weaponized on port 5000... 🚀              ")
    print(" Network IP deployment listener active on http://0.0.0.0:5000      ")
    print("------------------------------------------------------------------")
    serve(app, host='0.0.0.0', port=5000)