import json
import os
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode, urlparse
from urllib.request import urlopen

from flask import Flask, abort, redirect, render_template, request, url_for
from sqlalchemy.exc import SQLAlchemyError

from data_manager import DataManager
from models import Movie, db


def create_app(test_config=None):
    app = Flask(__name__)
    data_dir = Path(__file__).resolve().parent / 'data'
    app.config.from_mapping(
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{(data_dir / 'movies.db').as_posix()}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        OMDB_API_KEY=os.environ.get('OMDB_API_KEY'),
    )
    if test_config:
        app.config.update(test_config)
    db.init_app(app)
    manager = DataManager()

    def init_database():
        data_dir.mkdir(exist_ok=True)
        manager.init_database()

    app.cli.command('init-db')(init_database)
    app.extensions['init_database'] = init_database

    def require_user(user_id):
        user = manager.get_user(user_id)
        if user is None:
            abort(404)
        return user

    def require_movie(user_id, movie_id):
        require_user(user_id)
        movie = manager.get_movie(movie_id)
        if movie is None or movie.user_id != user_id:
            abort(404)
        return movie

    def form_text(field, label, maximum):
        value = request.form.get(field, '').strip()
        if not value or len(value) > maximum:
            abort(400, description=f'Please enter {label} between 1 and {maximum} characters.')
        return value

    @app.route('/')
    def home():
        return render_template('index.html', users=manager.get_users())

    @app.route('/users', methods=['POST'])
    def create_user():
        manager.create_user(form_text('name', 'a name', 100))
        return redirect(url_for('home'))

    @app.route('/users/<int:user_id>/movies', methods=['GET'])
    def list_movies(user_id):
        user = require_user(user_id)
        return render_template('movies.html', user=user, movies=manager.get_movies(user_id))

    @app.route('/users/<int:user_id>/movies', methods=['POST'])
    def add_movie(user_id):
        require_user(user_id)
        title = form_text('title', 'a movie title', 200)
        api_key = app.config.get('OMDB_API_KEY')
        if not api_key:
            abort(503, description='Movie search is not configured. Please set OMDB_API_KEY.')
        query = urlencode({'apikey': api_key, 't': title})
        try:
            with urlopen(f'https://www.omdbapi.com/?{query}', timeout=10) as response:
                info = json.load(response)
        except (URLError, OSError, ValueError):
            # Network exceptions can contain the request URL and API key.
            app.logger.warning('OMDb request failed.')
            abort(502, description='Movie search is unavailable. Please try again later.')
        if not isinstance(info, dict):
            abort(502, description='Movie search returned an invalid response.')
        if info.get('Response') == 'False':
            if info.get('Error') == 'Movie not found!':
                abort(400, description='No movie found. Please try another title.')
            abort(502, description='Movie search could not complete the request.')
        name = metadata(info, 'Title', 200)
        if info.get('Response') != 'True' or name is None:
            abort(502, description='Movie search returned an invalid response.')
        poster = metadata(info, 'Poster', 1000)
        if poster:
            try:
                parsed_poster = urlparse(poster)
                if parsed_poster.scheme not in ('http', 'https') or not parsed_poster.netloc:
                    poster = None
            except ValueError:
                poster = None
        manager.add_movie(Movie(
            name=name, director=metadata(info, 'Director', 200),
            year=metadata(info, 'Year', 20), poster_url=poster, user_id=user_id,
        ))
        return redirect(url_for('list_movies', user_id=user_id))

    @app.route('/users/<int:user_id>/movies/<int:movie_id>/update', methods=['POST'])
    def update_movie(user_id, movie_id):
        require_movie(user_id, movie_id)
        manager.update_movie(movie_id, form_text('title', 'a title', 200))
        return redirect(url_for('list_movies', user_id=user_id))

    @app.route('/users/<int:user_id>/movies/<int:movie_id>/delete', methods=['POST'])
    def delete_movie(user_id, movie_id):
        require_movie(user_id, movie_id)
        manager.delete_movie(movie_id)
        return redirect(url_for('list_movies', user_id=user_id))

    @app.errorhandler(SQLAlchemyError)
    def database_error(error):
        db.session.rollback()
        app.logger.error('Database operation failed.', exc_info=True)
        return render_template('500.html'), 500

    @app.errorhandler(404)
    def not_found(error):
        return render_template('404.html'), 404

    @app.errorhandler(500)
    def server_error(error):
        return render_template('500.html'), 500

    def request_error(error):
        return render_template('error.html', error=error), error.code

    for status in (400, 502, 503):
        app.register_error_handler(status, request_error)

    return app


def metadata(info, key, maximum):
    value = info.get(key)
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value if value and value != 'N/A' and len(value) <= maximum else None


app = create_app()

if __name__ == '__main__':
    with app.app_context():
        app.extensions['init_database']()
    app.run()
