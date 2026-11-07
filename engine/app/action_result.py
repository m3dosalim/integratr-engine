# A plain result from one Engine action.
# Routes turn this into an HTTP status and a JSON body.


class ActionResult:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self.body = body


def ok(body):
    return ActionResult(200, body)


def reject(status_code, message):
    return ActionResult(status_code, {"errors": [message]})
