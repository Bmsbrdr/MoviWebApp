import io
import json
import unittest
from unittest.mock import patch
from urllib.error import URLError

from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app import create_app
from data_manager import DataManager
from models import Movie, db


class MoviWebTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({
            'TESTING': True,
            'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
            'OMDB_API_KEY': 'test-secret',
        })
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        self.client = self.app.test_client()
        self.manager = DataManager()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def user(self, name='Alex'):
        return self.manager.create_user(name).id

    def movie(self, user_id):
        movie = Movie(name='Arrival', director='Denis Villeneuve', year='2016', user_id=user_id)
        self.manager.add_movie(movie)
        return movie.id

    def omdb_post(self, user_id, payload):
        with patch('app.urlopen', return_value=io.BytesIO(json.dumps(payload).encode())) as fetch:
            response = self.client.post(f'/users/{user_id}/movies', data={'title': ' Arrival '})
            self.assertEqual(fetch.call_args.kwargs['timeout'], 10)
            return response

    def test_empty_pages_and_user_creation(self):
        self.assertIn(b'The first collection starts with you', self.client.get('/').data)
        response = self.client.post('/users', data={'name': '  Alex  '})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, '/')
        user = self.manager.get_users()[0]
        self.assertEqual(user.name, 'Alex')
        self.assertIn(b'No movies yet', self.client.get(f'/users/{user.id}/movies').data)

    def test_movie_lifecycle_and_title_only_update(self):
        user_id = self.user()
        response = self.omdb_post(user_id, {
            'Response': 'True', 'Title': 'Arrival', 'Director': 'Denis Villeneuve',
            'Year': '2016', 'Poster': 'https://example.com/poster.jpg',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.location, f'/users/{user_id}/movies')
        movie = self.manager.get_movies(user_id)[0]
        movie_id = movie.id
        page = self.client.get(response.location)
        self.assertIn(b'Arrival', page.data)
        self.assertIn(b'https://example.com/poster.jpg', page.data)
        response = self.client.post(f'/users/{user_id}/movies/{movie_id}/update', data={'title': '  My Arrival  '})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(movie.name, 'My Arrival')
        self.assertEqual((movie.director, movie.year), ('Denis Villeneuve', '2016'))
        response = self.client.post(f'/users/{user_id}/movies/{movie_id}/delete')
        self.assertEqual(response.status_code, 302)
        self.assertIsNone(self.manager.get_movie(movie_id))

    def test_missing_resources_and_ownership(self):
        owner = self.user()
        other = self.user('Sam')
        movie_id = self.movie(owner)
        self.assertEqual(self.client.get('/missing').status_code, 404)
        self.assertEqual(self.client.get('/users/999/movies').status_code, 404)
        self.assertEqual(self.client.post('/users/999/movies', data={'title': 'Arrival'}).status_code, 404)
        self.assertEqual(self.manager.get_movies(other), [])
        for action in ('update', 'delete'):
            for user_id, target in ((other, movie_id), (owner, 999), (999, movie_id)):
                response = self.client.post(f'/users/{user_id}/movies/{target}/{action}', data={'title': 'Changed'})
                self.assertEqual(response.status_code, 404)
                self.assertIn(b'This scene is', response.data)
        self.assertEqual(self.manager.get_movie(movie_id).name, 'Arrival')

    def test_invalid_form_values(self):
        user_id = self.user()
        movie_id = self.movie(user_id)
        for name in ('', '   ', 'x' * 101):
            self.assertEqual(self.client.post('/users', data={'name': name}).status_code, 400)
        for title in ('', '   ', 'x' * 201):
            for url in (f'/users/{user_id}/movies', f'/users/{user_id}/movies/{movie_id}/update'):
                self.assertEqual(self.client.post(url, data={'title': title}).status_code, 400)
        self.assertEqual(len(self.manager.get_users()), 1)
        self.assertEqual(self.manager.get_movie(movie_id).name, 'Arrival')

    def test_missing_metadata_and_escaping(self):
        user_id = self.user('<script>alert(1)</script>')
        response = self.omdb_post(user_id, {
            'Response': 'True', 'Title': '<script>movie</script>',
            'Director': 'N/A', 'Year': 'N/A', 'Poster': 'N/A',
        })
        self.assertEqual(response.status_code, 302)
        movie = self.manager.get_movies(user_id)[0]
        self.assertIsNone(movie.poster_url)
        self.assertIsNone(movie.director)
        page = self.client.get(response.location).data
        self.assertIn(b'Poster unavailable', page)
        self.assertIn(b'Unknown', page)
        self.assertNotIn(b'<script>', page)
        self.assertIn(b'&lt;script&gt;', page)

    def test_omdb_failures(self):
        user_id = self.user()
        url = f'/users/{user_id}/movies'
        self.app.config['OMDB_API_KEY'] = None
        self.assertEqual(self.client.post(url, data={'title': 'Arrival'}).status_code, 503)
        self.app.config['OMDB_API_KEY'] = 'test-secret'
        for payload, status in (
            ({'Response': 'False', 'Error': 'Movie not found!'}, 400),
            ({'Response': 'False', 'Error': 'Invalid API key!'}, 502),
            ([], 502), ({}, 502),
            ({'Response': 'True', 'Title': ['invalid']}, 502),
        ):
            with self.subTest(payload=payload):
                self.assertEqual(self.omdb_post(user_id, payload).status_code, status)
        for error in (URLError('test-secret'), TimeoutError('test-secret')):
            with patch('app.urlopen', side_effect=error), self.assertLogs(self.app.logger, 'WARNING') as logs:
                response = self.client.post(url, data={'title': 'Arrival'})
            self.assertEqual(response.status_code, 502)
            self.assertNotIn('test-secret', ''.join(logs.output))
            self.assertNotIn(b'test-secret', response.data)
        with patch('app.urlopen', return_value=io.BytesIO(b'not json')):
            self.assertEqual(self.client.post(url, data={'title': 'Arrival'}).status_code, 502)
        self.assertEqual(self.manager.get_movies(user_id), [])

    def test_failed_commit_rolls_back_and_recovers(self):
        with patch.object(db.session, 'commit', side_effect=SQLAlchemyError('simulated failure')):
            with patch.object(db.session, 'rollback', wraps=db.session.rollback) as rollback:
                with self.assertRaises(SQLAlchemyError):
                    self.manager.create_user('Failed user')
                rollback.assert_called_once()
        self.assertEqual(self.manager.get_users(), [])
        self.user('Recovered user')
        self.assertEqual(self.manager.get_users()[0].name, 'Recovered user')

    def test_database_failure_page_and_recovery(self):
        with patch.object(db.session, 'commit', side_effect=SQLAlchemyError('private details')):
            with self.assertLogs(self.app.logger, 'ERROR'):
                response = self.client.post('/users', data={'name': 'Failed'})
        self.assertEqual(response.status_code, 500)
        self.assertIn(b'intermission', response.data)
        self.assertNotIn(b'private details', response.data)
        self.assertEqual(self.client.post('/users', data={'name': 'Recovered'}).status_code, 302)
        self.assertEqual([user.name for user in self.manager.get_users()], ['Recovered'])

    def test_cli_initialization(self):
        result = self.app.test_cli_runner().invoke(args=['init-db'])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(self.manager.get_users(), [])

    def test_real_integrity_error_rolls_back(self):
        with self.assertRaises(IntegrityError):
            self.manager.create_user(None)
        self.user('After rollback')
        self.assertEqual([user.name for user in self.manager.get_users()], ['After rollback'])

    def test_year_ranges_and_invalid_posters(self):
        user_id = self.user()
        for poster in ('N/A', 'javascript:alert(1)', 'https://[broken', 'https:relative'):
            with self.subTest(poster=poster):
                response = self.omdb_post(user_id, {
                    'Response': 'True', 'Title': 'A series', 'Year': '2001–2004',
                    'Poster': poster,
                })
                self.assertEqual(response.status_code, 302)
        for movie in self.manager.get_movies(user_id):
            self.assertIsNone(movie.poster_url)
            self.assertEqual(movie.year, '2001–2004')

    def test_read_failure_uses_server_error_page(self):
        with patch.object(DataManager, 'get_users', side_effect=SQLAlchemyError('private details')):
            with self.assertLogs(self.app.logger, 'ERROR'):
                response = self.client.get('/')
        self.assertEqual(response.status_code, 500)
        self.assertNotIn(b'private details', response.data)
        self.assertIn(b'intermission', response.data)


if __name__ == '__main__':
    unittest.main()
