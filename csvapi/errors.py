class APIError(Exception):
    status = 500

    def __init__(self, message, status=None, payload=None):
        Exception.__init__(self)
        self.message = message
        if status is not None:
            self.status = status
        self.payload = payload

    def to_dict(self):
        rv = dict(self.payload or ())
        rv['error'] = self.message
        rv['ok'] = False
        return rv
