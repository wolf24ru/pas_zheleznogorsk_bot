from datetime import datetime

import requests
from bs4 import BeautifulSoup
from datetime import datetime
from telegram_django_bot.tg_dj_bot import TG_DJ_Bot
from bot_conf.settings import TELEGRAM_TOKEN
from base.models import User, Pass_User, SNILS
from django_cron import CronJobBase, Schedule
from fake_useragent import UserAgent

def _pass_downloaded(snils: str) -> list:
    url = "https://sibghk.ru/propuski/"
    ua = UserAgent()
    headers = {"user-agent": ua.random}
    snils_list = [int(snils[0:3]),
                  int(snils[3:6]),
                  int(snils[6:9]),
                  int(snils[9:])]
    data = []
    session = requests.Session()
    session.headers.update(headers)
    r = session.get(url)
    print(f'status cod to get csrf{r.status_code}')
    soup = BeautifulSoup(r.content, "html.parser")
    csrf = soup.find("input", {"name": "_csrf"})["value"]
    payload = {
        "_csrf": csrf,
        "SnilsForm[snils1]": snils_list[0],
        "SnilsForm[snils2]": snils_list[1],
        "SnilsForm[snils3]": snils_list[2],
        "SnilsForm[snils4]": snils_list[3],
    }
    r = session.post(url, data=payload)
    print(f'status code to get data{r.status_code}')
    soup = BeautifulSoup(r.content, 'html.parser')
    tables = soup.find_all("table")
    for table in tables:
        for row in table.find_all("tr"):
            cols = row.find_all("td")
            cols = [ele.text.strip() for ele in cols]
            if cols:
                data.append({
                    "surname": cols[0],
                    "initial_n": cols[1].removesuffix('.'),
                    "initial_p": cols[2].removesuffix('.'),
                    "status_solution": cols[3],
                    "bb_date": cols[4],
                    "snils": snils
                })
    return data


def _get_data(snils_list) -> list:
    data = []
    if snils_list:
        for snils in snils_list:
            data += _pass_downloaded(snils)
    else:
        print('snils list is empty')
    return data


def _date_transform(date: str) -> datetime:
    if date:
        dt = date.split('.')
        return datetime(int(dt[2]), int(dt[1]), int(dt[0])).date()


def send_message(rg_user: object, text: str):
    # user = User.objects.get(user=rg_user)
    bot = TG_DJ_Bot(TELEGRAM_TOKEN)
    bot.send_message(rg_user.id, text)


def _create_user_in_db(person):
    pass_users = Pass_User.objects.all()
    try:
        pass_u = pass_users.get(surname=person['surname'],
                                name=person['initial_n'],
                                patronymic=person['initial_p'])
    except Pass_User.DoesNotExist:
        pass_u = Pass_User(
            surname=person['surname'],
            name=person['initial_n'],
            patronymic=person['initial_p'],
            status_solution=person['status_solution'],
            bb_date=_date_transform(person['bb_date']))
        pass_u.save()
        SNILS.objects.get(number=person['snils']).pass_user.add(pass_u)
    else:
        db_bb_date = pass_u.bb_date
        new_bb_date = _date_transform(person['bb_date'])
        if new_bb_date and db_bb_date:
            time_difference = (new_bb_date - db_bb_date).day
            if time_difference:
                pass_u.bb_date = new_bb_date
                pass_u.status_solution = person['status_solution']
                pass_u.save()


def _comparison(new_pass, db_pass):
    """Сравнение новой записи и старой с дальнейшим изменением,
    в случае если её нет, то добавление в бд записи"""
    if new_pass:
        np = False
        for person in new_pass:
            try:
                db_person = db_pass.get(surname=person['surname'],
                                        name=person['initial_n'],
                                        patronymic=person['initial_p'])
                if person['surname'] == 'ГУЛЯЕВ':
                    np = True
                    print(db_person)
                    print(f'db_person.date={db_person.bb_date}')
            except Pass_User.DoesNotExist:
                _create_user_in_db(person)
            else:
                new_bb_date_empty = False
                if person['bb_date'] and db_person.bb_date:
                    db_bb_date = db_person.bb_date
                    new_bb_date = _date_transform(person['bb_date'])
                    time_difference = (new_bb_date - db_bb_date).days
                    days_to_end = db_bb_date - datetime.now().date()
                else:
                    # todo придумать что делать если пропуск уже кончился
                    #  и теперь кончается разрешение
                    time_difference = -1

                    if db_person.bb_date:
                        db_bb_date = db_person.bb_date
                        days_to_end = db_bb_date - datetime.now().date()
                        new_bb_date_empty = True
                        if np:
                            print(f'in Ilya have db_person.bb_date={db_person.bb_date}')
                    elif person['bb_date']:
                        new_bb_date = _date_transform(person['bb_date'])
                        days_to_end = new_bb_date - datetime.now().date()
                        db_bb_date_empty = True
                        if np:
                            print(f'new_bb_date ={new_bb_date}')
                            print(f'days_to_end ={days_to_end}')

                    else:
                        days_to_end = -1

                status_change = db_person.status_solution == person['status_solution']
                if np:
                    print(f'status_change= {status_change}')
                is_change = False
                if time_difference == 0 and status_change:
                    db_person.status_solution = person['status_solution']
                    is_change = True
                if ((time_difference and status_change)
                        or
                        (not db_person.bb_date and
                         person['bb_date'] and
                         days_to_end and status_change)
                        or
                        (not time_difference and
                         new_bb_date_empty and
                         not days_to_end and
                         status_change)):
                    db_person.status_solution = person['status_solution']
                    db_person.bb_date = _date_transform(person['bb_date'])
                    is_change = True
                    if np:
                        print('change now')
                        print(f'db_person={db_person}')
                db_person.save()
                subscriptions_list = db_person.telegram_users.all()
                    # todo пока что так. потом придумать как запихивать
                    #  все изменения в одно сообщение. что бы пользователь
                    #  получал сообщение не по одному изменению, а все сразу
                if subscriptions_list and is_change:
                    if days_to_end != 60:
                        # todo придумать что сделать с этим местом. В данный момент бот должен напоминать о том что осталось 60 дней каждый раз как заходит сюда в течении всего дня
                        text = f'По вашей подписки имеется обновление:\n'
                    else:
                        text = f'До окончания действия пропуска осталось 60 дней '
                    text += (f'{db_person.surname}. {db_person.name}. {db_person.patronymic}\n'
                             f'Статус: {db_person.status_solution}\n')
                    if db_person.bb_date:
                        text += (f'Дата окончания пропуска {db_person.show_date()}\n'
                                 f'До окончания действия пропуска:{(db_person.bb_date - datetime.now().date()).days} дней')
                    for rg_user in subscriptions_list:
                        send_message(rg_user, text)
    else:
        print('error request')
        assert 'error request'
    # elif new_pass and not db_pass:
    #     # заполняем пустую базу


class CheckPassUpdates(CronJobBase):
    RUN_EVERY_MINS = 120
    schedule = Schedule(run_every_mins=RUN_EVERY_MINS)
    code = 'base.check_pass_updates'

    def do(self):
        # * / 5 6 - 21 / 2 * * *
        print(datetime.now())
        db_pass = Pass_User.objects.all()

        all_snils = [str(i.number) for i in SNILS.objects.all()]

        new_downloaded_pass = _get_data(all_snils)

        _comparison(new_downloaded_pass, db_pass)

        # todo как-то необходимо сказать пользователю,что в БД есть изменения
        # * / 5 ** ** source /home/user/.bashrc & & source / home / user / Nikita / pas_zheleznogorsk_bot / env / bin / activate & & python / home / user / Nikita / pas_zheleznogorsk_bot / manage.py
        # runcrons > / home / user / Nikita / pas_zheleznogorsk_bot / cronjob.log
# * * / 5 6 - 21 / 2 * * * /pass_bot/manage.py runcrons  >> /cron/logs/cronjob.log
