from django.core.management.commands.runserver import Command as RunserverCommand


class Command(RunserverCommand):
    def add_arguments(self, parser):
        super().add_arguments(parser)
        parser.set_defaults(addrport='localhost:8000')
