from models import db, User, Movie
from sqlalchemy.exc import SQLAlchemyError


class DataManager:
    def get_user(self, user_id):
        return db.session.get(User, user_id)

    def get_movie(self, movie_id):
        return db.session.get(Movie, movie_id)

    def _save(self, operation):
        try:
            operation()
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            raise

    def init_database(self):
        db.create_all()

    def create_user(self, name):
        user = User(name=name)
        self._save(lambda: db.session.add(user))
        return user

    def get_users(self):
        return db.session.execute(db.select(User).order_by(User.id)).scalars().all()

    def get_movies(self, user_id):
        return db.session.execute(
            db.select(Movie).where(Movie.user_id == user_id).order_by(Movie.id)
        ).scalars().all()

    def add_movie(self, movie):
        self._save(lambda: db.session.add(movie))

    def update_movie(self, movie_id, new_title):
        movie = self.get_movie(movie_id)
        if movie is None:
            raise ValueError('Movie not found.')
        self._save(lambda: setattr(movie, 'name', new_title))

    def delete_movie(self, movie_id):
        movie = self.get_movie(movie_id)
        if movie is None:
            raise ValueError('Movie not found.')
        self._save(lambda: db.session.delete(movie))
