# MoviWebApp

A personal movie collection app built with Flask, SQLite, SQLAlchemy, and OMDb.
Choose a user, find movies by title, and manage their favorites in a dark cinema-inspired interface.

## Set up in PyCharm

1. Install Python 3.12 or newer and open this project in PyCharm.
2. Under **Settings > Project > Python Interpreter**, select a working interpreter
   or create a project virtual environment named `.venv`.
   If an existing environment points to a missing Python installation, select a
   working interpreter first and recreate the environment only when needed.
3. Install the dependencies in the terminal using the selected interpreter:

   ```powershell
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

4. Create a Python run configuration for `app.py`. Set the working directory to
   the project directory and add `OMDB_API_KEY=your-api-key` to its environment variables.
5. Run `app.py` and open http://localhost:5000.

## Run from PowerShell

```powershell
$env:OMDB_API_KEY = 'your-api-key'
.\.venv\Scripts\python.exe app.py
```

Keep your real API key out of source files and Git. The app reads it from the
process environment at startup; it does not automatically load `.env` files.
Without a key, users and existing collections still work, but movie search
returns a helpful error page.

Running `app.py` directly creates `data/movies.db` and any missing tables.
Existing records are preserved. `create_all()` does not migrate existing schemas.

For Flask CLI startup, initialize the database explicitly first:

```powershell
.\.venv\Scripts\python.exe -m flask --app app init-db
.\.venv\Scripts\python.exe -m flask --app app run
```

## Features and structure

- `models.py`: User and Movie models. Each movie entry belongs to one user.
- `data_manager.py`: database reads, writes, and transaction rollback on failure.
- `app.py`: application factory, routes, OMDb lookup, and HTTP error handling.
- `templates/` and `static/`: responsive pages, shared navigation, and cinema styling.
- `tests/`: automated tests using an isolated in-memory SQLite database and mocked OMDb responses.

Movie years are text because OMDb can return year ranges. Missing metadata is
shown as unknown, and unavailable posters have a placeholder. Updating a movie
changes its title only; it does not fetch new metadata from OMDb.

The routes are:

| Method | URL | Action |
| --- | --- | --- |
| GET | `/` | List users |
| POST | `/users` | Create a user |
| GET | `/users/<user_id>/movies` | Show a collection |
| POST | `/users/<user_id>/movies` | Add a movie from OMDb |
| POST | `/users/<user_id>/movies/<movie_id>/update` | Update the title |
| POST | `/users/<user_id>/movies/<movie_id>/delete` | Delete the movie |

## Run tests

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tests do not access OMDb or your saved movie database. They cover CRUD operations,
validation, ownership checks, missing resources, API failures, error pages, and
recovery after a failed database transaction.

For a manual check, create two users, add a movie, edit its title, and delete it.
Try the pages at desktop width and at 390px width, including keyboard navigation.

## Local use

This project is intended for local use. Selecting a user is not authentication.
Deployment is deferred; nothing is published automatically.
