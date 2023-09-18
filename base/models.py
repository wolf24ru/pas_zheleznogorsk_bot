from django.db import models
from telegram_django_bot.models import TelegramUser
from datetime import datetime


class Pass_User(models.Model):
    """
    Дополнительные данные пользователей
    получающих данные об пропусках через Телеграмм
    """

    surname = models.CharField(max_length=150,
                               db_comment="Фамилия",
                               verbose_name="Фамилия")
    name = models.CharField(max_length=150,
                            db_comment="Имя",
                            verbose_name="Имя")
    patronymic = models.CharField(max_length=150,
                                  db_comment="Отчество",
                                  verbose_name="Отчество",
                                  blank=True,
                                  null=True)
    status_solution = models.CharField(max_length=200,
                                       db_comment="Решение",
                                       verbose_name="Решение")
    bb_date = models.DateField(db_comment="Дата окончания",
                               verbose_name="Дата окончания",
                               blank=True,
                               null=True)
    update_date = models.DateField(db_comment="День обновления",
                                   verbose_name="День обновления",
                                   default=datetime.today(),
                                   blank=True,
                                   null=True)

    def show_in_list(self):
        days_left = (self.bb_date - datetime.now().date()).days
        if days_left > 0:
            return True
        else:
            return False

    def show_date(self):
        return f'{self.bb_date.day}.{self.bb_date.month}.{self.bb_date.year}'

    def __str__(self):
        if self.bb_date:
            return f'{self.surname}. {self.name}. {self.patronymic} - осталось {(self.bb_date - datetime.now().date()).days} дней'
        else:
            return f'{self.surname}. {self.name}. {self.patronymic}'


class User(TelegramUser):
    FAVORITE_ICON = {
        False: '🤍 ',
        True: '❤️ '
    }

    date = models.PositiveIntegerField(default=60,
                                       db_comment='Дней до напоминания',
                                       verbose_name='Дней до напоминания')

    subscriptions = models.ManyToManyField(Pass_User,
                                           verbose_name="Избранное",
                                           db_constraint="Избранное",
                                           related_name="telegram_users",
                                           related_query_name="telegram_user_s",
                                           blank=True)


class SNILS(models.Model):
    name = models.CharField(max_length=150,
                            db_comment="Имя СНИЛС",
                            verbose_name="Имя СНИЛС",
                            blank=True)
    number = models.CharField(max_length=20,
                              db_comment="Номер СНИЛС",
                              verbose_name="Номер СНИЛС",
                              unique=True)
    users_snils = models.ManyToManyField(User,
                                         verbose_name='Пользователи',
                                         related_name='snilss',
                                         related_query_name='snils')
    pass_user = models.ManyToManyField(Pass_User,
                                       verbose_name='Список пропусков',
                                       related_name='snils_pass',
                                       related_query_name='snils_pass_s',
                                       blank=True)

    def __str__(self):
        return f'{self.name} - {self.number}'
