from functools import wraps
from flask import Flask, redirect, url_for, session, flash, render_template, request, abort
from flask.ext.sqlalchemy import SQLAlchemy
from flaskext.markdown import Markdown
from werkzeug.contrib.cache import SimpleCache

import re
from datetime import datetime
from config import config

cache = SimpleCache()

app = Flask(__name__)

app.debug = True
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql://xling:flask@localhost/forum'

#app.config['USER'] = 'admin'
#app.config['PASSWORD'] = 'default'
app.config['SECRET_KEY'] = 'C5G94WB6BVRPHTO85RGI2Y6TM6HYY0P'


for key in config:
    app.config[key] = config[key]


def cached(timeout=5 * 60, key='cached/%s'):
    # ~200 req/s => ~600-800 req/s
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            cache_key = key % request.path
            rv = cache.get(cache_key)
            if rv is not None:
                return rv
            rv = f(*args, **kwargs)
            cache.set(cache_key, rv, timeout=timeout)
            return rv
        return decorated_function
    return decorator

slug_re = re.compile('[a-zA-Z0-9]+')

db = SQLAlchemy(app)
Markdown(app)


def slugify(title):
    _title = title[:99].replace(' ', '-')  # Changed slug length to 100
    return '-'.join(re.findall(slug_re, _title))


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        logged = session.get('username', None)
        if not logged:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(30), unique=True)
    email = db.Column(db.String(100), unique=True)
    pic = db.Column(db.String(100), unique=True, nullable=True)
    password = db.Column(db.String(30))
    status = db.Column(db.Integer, default=0)
    gid = db.Column(db.Integer, default=0)
    join = db.Column(db.DateTime)
    posts = db.relationship('Post', backref='user', lazy='dynamic')
    replay = db.relationship('Reply', backref='user', lazy='dynamic')

    def __init__(self, username, password, email):
        self.username = username
        self.password = password
        self.email = email
        self.join = datetime.now()

    def __repr__(self):
        return '<user %r>' % self.username
        
class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(60))
    html = db.Column(db.Text)
    created = db.Column(db.DateTime)
    author = db.Column(db.String(30), db.ForeignKey('user.username'))
    replay = db.relationship('Reply', backref='posts', lazy='dynamic')

    def __init__(self, title, rawbody, author):
        self.title = title
        self.html = rawbody  # TODO: markdown support
        self.created = datetime.now()
        self.author = author  # added author to the Post object

    def __repr__(self):
        return '<post %r>' % self.title


class Reply(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'))
    author = db.Column(db.String(30), db.ForeignKey('user.username'))
    content = db.Column(db.Text)
    ctime = db.Column(db.DateTime)

    def __init__(self, author, content, post_id):
        self.author = author
        self.content = content
        self.ctime = datetime.now()
        self.post_id = post_id

    def __repr__(self):
        return '<replay %r>' % self.content[:10]

@app.template_filter('friendlytime')
def timesince(dt):
    format = "%A, %B %d, %Y"
    #return dt.isoformat()
    return dt.strftime(format)
    #return default


@app.route('/')
#@cached(120)  # from 200 req/s to 800 req/s
def index():
    posts = Post.query.order_by('created DESC')
    #posts = Post.query.order_by('created DESC').limit(app.config['post_count'])
    # Ordering by created time DESC isstead of reversing
    return render_template('index.html', posts=posts)

@app.route('/personcenter/<name>')
@login_required
def personcenter(name):
    user = User.query.filter_by(username=name).first()
    posts = Post.query.filter_by(author=name).order_by('id desc')
    replies = Reply.query.filter_by(author=name).order_by('id desc')

    return render_template('personcenter.html', posts=posts, user=user, replies=replies)

@app.route('/p/<int:id>/')
#@cached(120)
def detail(id):
    post = Post.query.filter_by(id=id).first()
    replies = Reply.query.filter_by(post_id = id).all()
    if post:
        return render_template('detail.html', post=post,replies=replies)
    else:
        abort(404)


@app.route('/new/', methods=['GET', 'POST'])
@login_required
def newpost():
    if request.method == 'POST':
        try:
            title = request.form['title']
            body = request.form['body']
            author = request.form['author']

        except Exception as e:
            flash('There was an error with your input: %s' % e)
            return redirect(url_for('newpost'))
        for thing in request.form.keys():  # verification
            if not request.form[thing]:
                flash('Error: %s incorrect.' % thing)
                return redirect(url_for('newpost'))

        p = Post(title, body, author)
        db.session.add(p)
        db.session.commit()
        return redirect(url_for('personcenter', name=session['username']))
    else:
        return render_template('new.html')


@app.route('/edit/<int:id>/', methods=['GET', 'POST'])
@login_required
def edit(id):
    if request.method == 'POST':
        try:
            title = request.form['title']
            body = request.form['body']
        except Exception as e:
            flash('There was an error with your input: %s' %e)
            return redirect(url_for('edit'))
        for thing in request.form.keys():
            if not request.form[thing]:
                flash('Error: %s incorrect.' % thing)
                return redirect(url_for('edit'))

       # p = Post.query.filter_by(id=id).update({"title":title, "body":body})
       # db.session.commit()
        post = Post.query.get(id)
        post.title = title
        post.html = body
        db.session.commit()
        return redirect(url_for('detail', id=id))
    else:
        post = Post.query.filter_by(id=id).first()
        return render_template('edit.html', post=post)

@app.route('/delete/<int:id>/')
@login_required
def delete(id):
    post = Post.query.filter_by(id=id).first()
    replies = Reply.query.filter_by(post_id=id).all()
    if replies:
        flash("Couldn't delete. No Post Or it had replies.")
    else:
        db.session.delete(post)
        db.session.commit()
        flash("Post deleted.")
        
    return redirect(url_for('personcenter', name=session['username']))

@app.route('/reply/<int:id>', methods=['GET', 'POST'])
@login_required
def reply(id):
    if request.method == 'POST':
        post_id = id
        author = session['username']        
        content = request.form['content']
        db.session.add(Reply(author, content, post_id))
        db.session.commit()

        return redirect(url_for('detail', id=id))

@app.route('/register/', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        #gid = 0

        db.session.add(User(username, password, email))
        db.session.commit()
        flash('You registered successfully.')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login/', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username).first()

        if user and user.username == username and user.password == password:
            session['username'] = request.form['username']
            session['gid'] = user.gid
            flash('You were logged in.')
            return redirect(url_for('personcenter', name=username))
    return render_template('login.html', error=error)


@app.route('/logout/')
@login_required
def logout():
    session.pop('username', None)
    flash('You were logged out.')
    return redirect(url_for('index'))

@app.route('/manauser/')
@login_required
def manauser():
    users = User.query.order_by('id DESC')
    return render_template('manauser.html', users=users)

@app.route('/manapost/')
@login_required
def manapost():
    posts = Post.query.order_by('id DESC')
    return render_template('manapost.html', posts=posts)

@app.route('/deluser/<int:id>/')
@login_required
def deluser(id):
    user = User.query.filter_by(id=id).first()
    posts = Post.query.filter_by(author=user.username).all()
    replies = Reply.query.filter_by(author=user.username).all()
    if user:
        db.session.delete(user)
        if posts:
            db.session.delete(posts)
            if replies:
                db.session.delete(replies)
        db.session.commit()
        flash(" the User and his/her Post/replies deleted.")
        
    return redirect(url_for('manauser'))

@app.route('/delpost/<int:id>/')
@login_required
def delpost(id):
    post = Post.query.filter_by(id=id).first()
    replies = Reply.query.filter_by(post_id=id).all()
    if post:
        db.session.delete(post)
        if replies:
            db.session.delete(replies)
        db.session.commit()
        flash(" the Post and its replies deleted.")
        
    return redirect(url_for('manapost'))

if __name__ == '__main__':
    debug = True
    app.run()
