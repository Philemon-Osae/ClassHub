from flask import Flask, render_template, request, redirect, session, flash
from supabase import create_client
import os, json, time
from dotenv import load_dotenv
from werkzeug.utils import secure_filename

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")
URL = os.getenv("SUPABASE_URL")
ANON = os.getenv("SUPABASE_ANON_KEY")
db = create_client(URL, ANON)

COURSES = [
    {"code": "CICS 111", "name": "Principles of Programming", "lecturer": "Dr. Michael Agbeko", "credits": 3},
    {"code": "CICS 151", "name": "Microcomputer Applications", "lecturer": "Dr. Bibi Dora Appiah", "credits": 3},
    {"code": "CIBS 115", "name": "Introduction to Computer Systems", "lecturer": "Mr. Solomon Abban", "credits": 3},
    {"code": "MATH 123", "name": "Computational Mathematics", "lecturer": "Mr. John Essuman", "credits": 3},
    {"code": "CIST 155", "name": "Sociology of Technology", "lecturer": "Dr. Seth Frimpong", "credits": 3},
    {"code": "MATH 127", "name": "Discrete Mathematics", "lecturer": "Dr. Isaac Appiah", "credits": 3},
    {"code": "EREN 171", "name": "Functional French", "lecturer": "Dr. Michael Owusu Tabiri", "credits": 2},
    {"code": "GEN AFR", "name": "African Studies", "lecturer": "Dr. Boakye Broyva", "credits": 2},
    {"code": "CIMP 235", "name": "Fundamentals of Mobile Computing", "lecturer": "Dr. Wendy Jasmine Odoro", "credits": 3},
]

def get_user(): return session.get('user')
def is_rep(): return get_user() and get_user().get('role')=='rep'

@app.route('/')
def index():
    user=get_user()
    if not user: return render_template('login.html')
    t=db.table('timetables').select('*').order('created_at', desc=True).limit(1).execute().data
    timetable=t[0] if t else None
    mats=db.table('materials').select('*').order('created_at', desc=True).limit(20).execute().data
    anon=db.table('anonymous_messages').select('course_code,message,reply,created_at').order('created_at', desc=True).limit(10).execute().data
    gpa_row=db.table('gpa_records').select('*').eq('user_id', user['id']).order('created_at', desc=True).limit(1).execute().data
    gpa=gpa_row[0]['gpa'] if gpa_row else None
    return render_template('dashboard.html', user=user, courses=COURSES, timetable=timetable, materials=mats, anon=anon, gpa=gpa)

@app.route('/login', methods=['POST'])
def login():
    idx=request.form.get('index','').strip()
    name=request.form.get('name','').strip()
    password=request.form.get('password','')
    rep_code=request.form.get('rep_code','').strip()
    if len(idx)!=10 or not name or len(password)<6:
        flash('Need 10-digit index, name, 6+ char password'); return redirect('/')
    email=f"{idx}@classhub.app"
    auth_client=create_client(URL, ANON)
    try:
        auth_res=auth_client.auth.sign_in_with_password({"email":email,"password":password})
    except:
        try:
            auth_res=auth_client.auth.sign_up({"email":email,"password":password,"options":{"data":{"index_number":idx,"full_name":name,"rep_code":rep_code}}})
        except Exception as e:
            flash(f'Failed: {str(e)[:250]}'); return redirect('/')
    for _ in range(6):
        try:
            u=db.table('users').select('*').eq('id', auth_res.user.id).single().execute().data
            if u:
                session['user']=u
                auth_client.auth.sign_out()
                return redirect('/')
        except: time.sleep(0.5)
    flash('Index not in roster or invalid rep code'); return redirect('/')

@app.route('/logout')
def logout():
    session.clear(); return redirect('/')

@app.route('/rep/timetable', methods=['GET','POST'])
def rep_timetable():
    if not is_rep(): return "Only reps",403
    if request.method=='POST':
        action=request.form.get('action')
        if action=='delete':
            db.table('timetables').delete().eq('id', request.form.get('id')).execute()
            flash('Deleted'); return redirect('/rep/timetable')
        if action=='upload':
            week_label=request.form.get('week_label','').strip()
            json_text=request.form.get('json_data','').strip()
            image_url=""
            file=request.files.get('timetable_image')
            if file and file.filename:
                fn=secure_filename(f"timetable-{int(time.time())}-{file.filename}")
                db.storage.from_('class-materials').upload(fn, file.read())
                image_url=db.storage.from_('class-materials').get_public_url(fn)
            json_data={}
            if json_text:
                try: json_data=json.loads(json_text)
                except: flash('Invalid JSON'); return redirect('/rep/timetable')
            db.table('timetables').insert({"week_label":week_label, "json_data":json_data, "image_url":image_url, "uploaded_by":get_user()['id']}).execute()
            flash('Uploaded'); return redirect('/rep/timetable')
    tables=db.table('timetables').select('*').order('created_at', desc=True).execute().data
    return render_template('rep_timetable.html', user=get_user(), timetables=tables)

@app.route('/rep/center')
def rep_center():
    if not is_rep(): return "Only reps",403
    mats=db.table('materials').select('*').order('created_at', desc=True).limit(30).execute().data
    anon=db.table('anonymous_messages').select('*').order('created_at', desc=True).execute().data
    return render_template('rep_center.html', user=get_user(), materials=mats, anon=anon, courses=COURSES)

@app.route('/rep/upload', methods=['POST'])
def rep_upload():
    if not is_rep(): return "Only reps",403
    course=request.form.get('course_code'); week=request.form.get('week'); mtype=request.form.get('type')
    file=request.files.get('file'); link=request.form.get('link','').strip()
    file_url=link; title=link or "Drive Link"
    if file and file.filename:
        fn=secure_filename(f"{int(time.time())}-{file.filename}")
        db.storage.from_('class-materials').upload(fn, file.read())
        file_url=db.storage.from_('class-materials').get_public_url(fn)
        title=file.filename
    if not file_url: return "Pick file or link",400
    db.table('materials').insert({"course_code":course,"week":week,"type":mtype,"title":title,"file_url":file_url,"uploaded_by":get_user()['id']}).execute()
    return redirect('/rep/center')

@app.route('/rep/material/delete', methods=['POST'])
def rep_delete_mat():
    if not is_rep(): return "Only reps",403
    db.table('materials').delete().eq('id', request.form.get('id')).execute()
    flash('Deleted'); return redirect('/rep/center')

@app.route('/student/ask', methods=['POST'])
def student_ask():
    if not get_user(): return "Login first",401
    db.table('anonymous_messages').insert({"course_code":request.form.get('course_code'),"message":request.form.get('message'),"is_anonymous":request.form.get('is_anonymous')=='on',"sender_id":get_user()['id']}).execute()
    flash('Sent'); return redirect('/')

@app.route('/rep/reply', methods=['POST'])
def rep_reply():
    if not is_rep(): return "Only reps",403
    db.table('anonymous_messages').update({"reply":request.form.get('reply')}).eq('id', request.form.get('id')).execute()
    flash('Replied'); return redirect('/rep/center')

@app.route('/gpa', methods=['GET','POST'])
def gpa_page():
    if not get_user(): return redirect('/')
    gpa_val=None
    if request.method=='POST':
        POINTS={"A":4.0,"B+":3.5,"B":3.0,"C+":2.5,"C":2.0,"D+":1.5,"D":1.0,"E":0.0}
        total_points=0; total_credits=0
        for c in COURSES:
            grade=request.form.get(c['code'],'B')
            total_points+=POINTS.get(grade,3.0)*c['credits']
            total_credits+=c['credits']
        gpa_val=round(total_points/total_credits,2) if total_credits else 0
        db.table('gpa_records').insert({"user_id":get_user()['id'],"gpa":gpa_val,"semester":"Sem1"}).execute()
        flash(f'GPA: {gpa_val}')
    return render_template('gpa.html', user=get_user(), courses=COURSES, gpa=gpa_val)

@app.route('/assignments')
def assignments_page():
    if not get_user(): return redirect('/')
    mats=db.table('materials').select('*').eq('type','Assignment').order('created_at', desc=True).execute().data
    return render_template('assignments.html', user=get_user(), assignments=mats)

@app.route('/past-questions')
def past_q():
    if not get_user(): return redirect('/')
    mats=db.table('materials').select('*').eq('type','Past Questions').order('created_at', desc=True).execute().data
    return render_template('past_questions.html', user=get_user(), materials=mats)

if __name__=='__main__':
    app.run(debug=False, port=5000)