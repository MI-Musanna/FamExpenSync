from sqlalchemy import Column, Integer, String, Float, ForeignKey, func
from sqlalchemy.orm import relationship
from database import Base, db_session
from datetime import datetime

class Member(Base):
    __tablename__ = 'members'
    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)
    pin = Column(String(4), nullable=False, default="1234")
    expenses = relationship('Expense', backref='member', lazy=True)
    categories = relationship('Category', backref='member', lazy=True)
    recurring_templates = relationship('RecurringTemplate', backref='member', lazy=True)

class Category(Base):
    __tablename__ = 'categories'
    id = Column(Integer, primary_key=True)
    name = Column(String(50), nullable=False)
    member_id = Column(Integer, ForeignKey('members.id'), nullable=False)
    expenses = relationship('Expense', backref='category', lazy=True)
    recurring_templates = relationship('RecurringTemplate', backref='category', lazy=True)

# NEW MODEL: Fixed Bills Template Storage
class RecurringTemplate(Base):
    __tablename__ = 'recurring_templates'
    id = Column(Integer, primary_key=True)
    member_id = Column(Integer, ForeignKey('members.id'), nullable=False)
    category_id = Column(Integer, ForeignKey('categories.id'), nullable=False)
    amount = Column(Float, nullable=False)
    description = Column(String(200))

class Expense(Base):
    __tablename__ = 'expenses'
    id = Column(Integer, primary_key=True)
    member_id = Column(Integer, ForeignKey('members.id'), nullable=False)
    category_id = Column(Integer, ForeignKey('categories.id'), nullable=False)
    amount = Column(Float, nullable=False)
    description = Column(String(200))
    date = Column(String(10), nullable=False)

class Setting(Base):
    __tablename__ = 'settings'
    key = Column(String(50), primary_key=True)
    value = Column(String(50), nullable=False)

def seed_data():
    if Member.query.count() == 0:
        m1 = Member(name="Father", pin="1234")
        m2 = Member(name="Mother", pin="1234")
        m3 = Member(name="Brother", pin="1234")
        m4 = Member(name="Me", pin="1234")
        db_session.add_all([m1, m2, m3, m4])
        db_session.commit()

        for m in Member.query.all():
            db_session.add_all([
                Category(name="Bazar", member_id=m.id),
                Category(name="Utilities", member_id=m.id),
                Category(name="Medical", member_id=m.id),
                Category(name="Transport", member_id=m.id)
            ])
        db_session.add(Setting(key="budget", value="50000"))
        # ইনিশিয়াল ক্রোনোলজিক্যাল ট্র্যাক স্টেট সেডিং
        db_session.add(Setting(key="last_recurring_month", value="1970-01"))
        db_session.commit()

# AUTOMATION ENGINE: স্বয়ংক্রিয়ভাবে নতুন মাসের শুরুতে ফিক্সড বিল জেনারেট করার লজিক
def check_and_generate_recurring_expenses():
    current_month = datetime.now().strftime('%Y-%m') # e.g., '2026-07'
    s = db_session.get(Setting, "last_recurring_month")
    if not s:
        s = Setting(key="last_recurring_month", value="1970-01")
        db_session.add(s)
        db_session.commit()
    
    if s.value < current_month:
        templates = RecurringTemplate.query.all()
        generated_date = f"{current_month}-01" # মাসের ১ম তারিখে এন্ট্রি হবে
        for t in templates:
            db_session.add(Expense(
                member_id=t.member_id,
                category_id=t.category_id,
                amount=t.amount,
                description=f"[Fixed Bill] {t.description}",
                date=generated_date
            ))
        s.value = current_month
        db_session.commit()

def get_all_members():
    return Member.query.all()

def get_categories_by_member(member_id):
    return Category.query.filter_by(member_id=member_id).all()

def add_new_expense(member_id, category_id, amount, description, date):
    db_session.add(Expense(member_id=member_id, category_id=category_id, amount=amount, description=description, date=date))
    db_session.commit()

def update_expense_by_id(id, member_id, category_id, amount, description, date):
    exp = db_session.get(Expense, id)
    if exp:
        exp.member_id = member_id
        exp.category_id = category_id
        exp.amount = amount
        exp.description = description
        exp.date = date
        db_session.commit()

def delete_expense_by_id(id):
    exp = db_session.get(Expense, id)
    if exp:
        db_session.delete(exp)
        db_session.commit()

def add_new_category(name, member_id):
    db_session.add(Category(name=name, member_id=member_id))
    db_session.commit()

def delete_category_by_id(id):
    cat = db_session.get(Category, id)
    if cat and Expense.query.filter_by(category_id=id).count() == 0:
        db_session.delete(cat)
        db_session.commit()

def get_budget():
    s = db_session.get(Setting, "budget")
    return float(s.value) if s else 50000.0

def update_budget(amount):
    s = db_session.get(Setting, "budget")
    if s: s.value = str(amount)
    db_session.commit()

def update_member_pin(member_id, old_pin, new_pin):
    member = db_session.get(Member, member_id)
    if member and member.pin == old_pin:
        if len(new_pin) == 4 and new_pin.isdigit():
            member.pin = new_pin
            db_session.commit()
            return True
    return False

# RECURRING MANAGEMENT HELPERS
def get_recurring_templates_by_member(member_id):
    return RecurringTemplate.query.filter_by(member_id=member_id).all()

def add_recurring_template(member_id, category_id, amount, description):
    db_session.add(RecurringTemplate(member_id=member_id, category_id=category_id, amount=amount, description=description))
    db_session.commit()

def delete_recurring_template_by_id(id):
    t = db_session.get(RecurringTemplate, id)
    if t:
        db_session.delete(t)
        db_session.commit()

def get_filtered_expenses(member_filter, time_filter, search_query=None):
    q = db_session.query(Expense)
    if member_filter != 'all':
        q = q.filter(Expense.member_id == int(member_filter))
        
    if time_filter == 'day':
        q = q.filter(Expense.date == func.date('now', 'localtime'))
    elif time_filter == 'week':
        q = q.filter(func.strftime('%Y-%W', Expense.date) == func.strftime('%Y-%W', 'now', 'localtime'))
    elif time_filter == 'month':
        q = q.filter(func.strftime('%Y-%m', Expense.date) == func.strftime('%Y-%m', 'now', 'localtime'))
    elif time_filter == 'year':
        q = q.filter(func.strftime('%Y', Expense.date) == func.strftime('%Y', 'now', 'localtime'))
        
    if search_query:
        q = q.filter(Expense.description.like(f"%{search_query}%"))
        
    return q.order_by(Expense.date.desc()).all()