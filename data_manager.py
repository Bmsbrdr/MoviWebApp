from models import db, User, Movie

class DataManager:
    def create_user(self, name):
        user = User(name=name)
        db.session.add(user)
        db.session.commit()
        return user

    def get_users(self):
        return db.session.execute(db.select(User).order_by(User.id)).scalars().all()

    def get_movies(self, user_id):
        return db.session.execute(
            db.select(Movie).where(Movie.user_id == user_id).order_by(Movie.id)
        ).scalars().all()

    def add_movie(self, movie):
        db.session.add(movie)
        db.session.commit()

    def update_movie(self, movie_id, new_title):
        movie = db.session.get(Movie, movie_id)
        if movie is None:
            raise ValueError('Movie not found.')
        movie.name = new_title
        db.session.commit()

    def delete_movie(self, movie_id):
        movie = db.session.get(Movie, movie_id)
        if movie is None:
            raise ValueError('Movie not found.')
        db.session.delete(movie)
        db.session.commit()
