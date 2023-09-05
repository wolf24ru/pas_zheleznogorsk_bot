#ARG PYTHON_VERSION=3.11-slim
ARG PYTHON_VERSION=3.11.0rc1

FROM python:${PYTHON_VERSION} as python-stage

# Install apt packages
RUN apt-get update && apt-get install --no-install-recommends -y \
  # dependencies for building Python packages
  build-essential \
  # psycopg2 dependencies
  libpq-dev      \
  # git+https
  git \
  python3-dev \
  graphviz \
  libgraphviz-dev \
  pkg-config \
  unixodbc-dev

COPY requirements.txt .
#RUN curl https://bootstrap.pypa.io/get-pip.py | python
#RUN pip install --upgrade pip==23.2.1

RUN pip install --upgrade pip
RUN pip install --upgrade setuptools
# Create Python Dependency and Sub-Dependency Wheels.
RUN --mount=type=cache,target=/root/.cache \
  pip wheel --wheel-dir /usr/src/app/wheels  \
  -r requirements.txt


FROM python:${PYTHON_VERSION} as python-run-stage
ENV PYTHONUNBUFFERED 1
ENV PYTHONDONTWRITEBYTECODE 1
ENV TZ="Asia/Krasnoyarsk"
WORKDIR /pass_bot

# Install required system dependencies
RUN apt-get update && apt-get install --no-install-recommends -y \
  # psycopg2 dependencies
  libpq-dev \
  # Translations dependencies
  gettext \
  libgeos-dev \
  npm \
  # task of cron
  cron \
  # cleaning up unused files
  && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
  && rm -rf /var/lib/apt/lists/*

COPY --from=python-stage /usr/src/app/wheels  /wheels/
RUN pip install --no-cache-dir --no-index --find-links=/wheels/ /wheels/* \
  && rm -rf /wheels/

RUN npm i -g nodemon

COPY ./docker-entrypoint.sh /docker-entrypoint.sh
RUN sed -i 's/\r$//g' /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh


COPY ./configs/commands/ /commands
RUN sed -i 's/\r$//g' /commands/*
RUN chmod +x -R /commands

COPY ./configs/confs /configs

#COPY ./configs/uwsgi_fuck /web/uwsgi/

#ENV UWSGI_WORKERS 4
#ENV UWSGI_THREADS 1

# copy application code to WORKDIR
COPY . /pass_bot
#RUN mkdir /pass_bot/logs && touch /pass_bot/logs/bot.log
#RUN crontab -l > /pass_bot/cron_job/new_cron && \
#    echo "* * / 5 6 - 21 / 2 * * * /pass_bot/manage.py runcrons  >> /cron/logs/cronjob.log" >> /pass_bot/cron_job/new_cron && \
#    crontab /pass_bot/cron_job/new_cron
RUN python manage.py makemigrations && python manage.py migrate
RUN mkdir cron_job
RUN touch /cron/logs/cronjob.log
RUN crontab -l | { cat; echo "0 6-21/1 * * * python /pass_bot/manage.py runcrons  >> /cron/logs/cronjob.log"; } | crontab -
#CMD crontab -l > /pass_bot/cron_job/new_cron && echo "* * / 5 6 - 21 / 2 * * * /pass_bot/manage.py runcrons  >> /cron/logs/cronjob.log" >> /pass_bot/cron_job/new_cron && crontab /pass_bot/cron_job/new_cron


CMD cron && tail -f /cron/logs/cronjob.log

ENTRYPOINT ["/docker-entrypoint.sh"]
