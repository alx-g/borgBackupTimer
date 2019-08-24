import shlex
import logging

flag = r'[[env]]'


def parse_terminal_command(cmd_str):
    global flag
    logging.debug('Parsing terminal command: %s', cmd_str)

    try:
        if flag not in cmd_str:
            logging.warning('Required flag "%s" is not contained in terminal_command. Terminal launch feature'
                            'disabled.', flag)
            return None

        p = parse(cmd_str, top=True)
        p('a a')
    except:
        logging.warning('Terminal command could not be parsed. Terminal launch feature disabled.')
        return None
    else:
        logging.debug('Successfully parsed and tested terminal command.')
        return p


def parse(sub_cmd, top=False):
    global flag
    if flag not in sub_cmd:
        return shlex.quote(sub_cmd)
    sp = shlex.split(sub_cmd)
    if len(sp) == 1:
        idx = sp[0].find(flag)
        return lambda x: sp[0][:idx] + str(x) + sp[0][idx+len(flag):]

    before = []
    after = []
    func = None
    for s in sp:
        parsed = parse(s)
        if callable(parsed):
            func = parsed
        else:
            if not func:
                before.append(parsed)
            else:
                after.append(parsed)
    if top:
        return lambda x: ' '.join(before + [func(x)] + after)
    else:
        return lambda x: shlex.quote(' '.join(before + [func(x)] + after))
