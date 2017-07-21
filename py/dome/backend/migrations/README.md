WARNING: files in this folder should **NOT** be modified in any circumstances!

If you want to change the database schema, you have to generate a new migration
file instead of modify the existing ones. Please read django's migration doc for
more information: https://docs.djangoproject.com/en/1.10/topics/migrations/

# How to Change Database Schema

Because Dome runs in Docker, you cannot simply run `manage.py makemigrations`
inside or outside chroot. You have you run this command in Dome's Docker
container.

Here's a brief instruction to make migrations:
- Modify the backend code.
- Run `setup/cros_docker.sh build`
- Run `setup/cros_docker.sh run`, if your change has modified the database
  schema, django would complain and tells you to make migrations.
- Go into the Docker container `docker exec -it dome_uwsgi sh`.
- Run `./manage.py makemigrations`.
- `exit` to get out from the Docker container.
- Pull the generated file out, if the newly generated file is called
  `0007_auto_20170411_0943.py`, then run `docker cp
  dome_uwsgi:/usr/local/factory/py/dome/backend/migrations/0007_auto_20170411_0943.py
  .`
- Modify the migration file if necessary, and run `pyformat` on it.
- Done!
