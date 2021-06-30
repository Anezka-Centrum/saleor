def prepare_params(params):
    prepared = {}
    for name, value in params.items():
        if value is True:
            value = 'true'
        elif value is False:
            value = 'false'
        prepared[name] = value
    return prepared
