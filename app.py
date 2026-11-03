import json
import os
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from flask import Flask, abort, redirect, render_template, request, url_for

from data_manager import DataManager
from models import Movie, User, db

app = Flask(__name__)
data_dir = Path(__file__).resolve().parent / 'data'
data_dir.mkdir(exist_ok=True)
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{(data_dir / 'movies.db').as_posix()}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)
data_manager = DataManager()


@app.route('/')
def home():
    return render_template('index.html', users=data_manager.get_users())


@app.route('/users', methods=['POST'])
def create_user():
    name = request.form.get('name', '').strip()
    if not name or len(name) > 100:
        abort(400, description='Please enter a name between 1 and 100 characters.')
    data_manager.create_user(name)
    return redirect(url_for('home'))


@app.route('/users/<int:user_id>/movies', methods=['GET'])
def list_movies(user_id):
    user = db.get_or_404(User, user_id)
    return render_template('movies.html', user=user, movies=data_manager.get_movies(user_id))


@app.route('/users/<int:user_id>/movies', methods=['POST'])
def add_movie(user_id):
    db.get_or_404(User, user_id)
    title = request.form.get('title', '').strip()
    if not title:
        abort(400, description='Please enter a movie title.')
    api_key = os.environ.get('OMDB_API_KEY')
    if not api_key:
        abort(503, description='The OMDB_API_KEY environment variable is missing.')
    query = urlencode({'apikey': api_key, 't': title})
    try:
        with urlopen(f'https://www.omdbapi.com/?{query}', timeout=10) as response:
            info = json.load(response)
    except (URLError, TimeoutError, ValueError):
        abort(502, description='Could not reach OMDb or read its response.')
    if not isinstance(info, dict):
        abort(502, description='Invalid response from OMDb.')
    if info.get('Response') != 'True' or not info.get('Title'):
        abort(400, description='Could not load the movie from OMDb. Please check the title and API key.')
    movie = Movie(
        name=info['Title'], director=info.get('Director'), year=info.get('Year'),
        poster_url=None if info.get('Poster') == 'N/A' else info.get('Poster'),
        user_id=user_id,
    )
    data_manager.add_movie(movie)
    return redirect(url_for('list_movies', user_id=user_id))


def get_user_movie(user_id, movie_id):
    db.get_or_404(User, user_id)
    movie = db.get_or_404(Movie, movie_id)
    if movie.user_id != user_id:
        abort(404)
    return movie


@app.route('/users/<int:user_id>/movies/<int:movie_id>/update', methods=['POST'])
def update_movie(user_id, movie_id):
    get_user_movie(user_id, movie_id)
    title = request.form.get('title', '').strip()
    if not title or len(title) > 200:
        abort(400, description='Please enter a title between 1 and 200 characters.')
    data_manager.update_movie(movie_id, title)
    return redirect(url_for('list_movies', user_id=user_id))


@app.route('/users/<int:user_id>/movies/<int:movie_id>/delete', methods=['POST'])
def delete_movie(user_id, movie_id):
    get_user_movie(user_id, movie_id)
    data_manager.delete_movie(movie_id)
    return redirect(url_for('list_movies', user_id=user_id))


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run()
