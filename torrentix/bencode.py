def _decode_str(bencode_str: bytes):
    delim = bencode_str.find(b':')
    size = int(bencode_str[:delim])
    string = bencode_str[delim + 1: delim + size + 1]
    try:
        string = string.decode()
    except UnicodeDecodeError:
        pass
    return string, delim + size + 1

def _decode_int(bencode_str: bytes):
    end = bencode_str.find(b'e')
    return int(bencode_str[1: end]), end+1

def _decode_list(bencode_str: bytes):
    ans = []
    bencode_str = bencode_str[1:]
    processed = 1
    while bencode_str and not bencode_str.startswith(b'e'):
        elem, size = _decode_unknown(bencode_str)
        bencode_str = bencode_str[size:]
        processed += size
        ans.append(elem)
    return ans, processed + 1

def _decode_dict(bencode_str: bytes):
    ans = {}
    bencode_str = bencode_str[1:]
    processed = 1
    while bencode_str and not bencode_str.startswith(b'e'):
        key, keysize = _decode_str(bencode_str)
        bencode_str = bencode_str[keysize:]
        val, valsize = _decode_unknown(bencode_str)
        bencode_str = bencode_str[valsize:]
        processed += keysize + valsize
        ans[key] = val
    return ans, processed + 1

def _decode_unknown(bencode_str: bytes):
    if bencode_str.startswith(b'i'):
        return _decode_int(bencode_str)
    elif bencode_str.startswith(b'l'):
        return _decode_list(bencode_str)
    elif bencode_str.startswith(b'd'):
        return _decode_dict(bencode_str)
    else:
        return _decode_str(bencode_str)

def decode(bencode_str: bytes):
    return _decode_unknown(bencode_str)[0]

def encode(obj):
    if isinstance(obj, bytes):
        return bytes(str(len(obj)), encoding='utf8') + b':' + obj
    elif isinstance(obj, str):
        return bytes(str(len(obj)), encoding='utf8') + b':' + bytes(obj, encoding='utf8')
    elif isinstance(obj, int):
        return b'i' + bytes(str(obj), encoding='utf8') + b'e'
    elif isinstance(obj, list):
        return b'l' +  b''.join(encode(i) for i in obj) + b'e'
    elif isinstance(obj, dict):
        return b'd' + b''.join(encode(i) + encode(obj[i]) for i in obj) + b'e'

if __name__ == '__main__':
    a = b"d8:intervali3600e5:peersld2:ip13:192.168.24.524:porti2001eed2:ip11:192.168.0.34:porti6889eeee"
    b = decode(a)
    print(b)
    c = encode(b)
    print(c)
    print(c == a)
