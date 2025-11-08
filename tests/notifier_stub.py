# -*- coding: utf-8 -*-
class NotifierStub:
    def __init__(self):
        self.msgs = []

    def parcial(self, cfg, **kw):
        self.msgs.append(("parcial", kw))

    def trailing(self, cfg, **kw):
        self.msgs.append(("trailing", kw))
