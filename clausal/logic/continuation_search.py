from greenlet import greenlet
from dataclasses import dataclass

class Finished(Exception):
    pass

class Search:
    def __init__(search, function, *args, **kwargs):
        search.function = function
        search.args = args
        search.kwargs = kwargs

    def __iter__(search):
        main = greenlet.getcurrent()

        def worker_fn():
            search.function(
                main.switch,
                *search.args,
                **search.kwargs
            )
            main.throw(Finished)

        worker = greenlet(worker_fn)

        try:
            while True:
                yield worker.switch()
        except Finished:
            return
