#!/usr/bin/env python3
"""Trello OAuth 2.0; credentials never printed or written in plaintext."""
import argparse, base64, fcntl, getpass, hashlib, json, os, secrets, subprocess, sys, tempfile, time
from pathlib import Path
from urllib.parse import urlencode, urlsplit, parse_qs
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

def request(url, method='GET', data=None, token=None):
    headers = {'Accept': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if data is not None:
        headers['Content-Type'] = 'application/json'
    req = Request(url, data=None if data is None else json.dumps(data).encode(), headers=headers, method=method)
    try:
        with build_opener(NoRedirect).open(req, timeout=40) as r:
            raw = r.read()
            return json.loads(raw) if raw else None
    except HTTPError as e:
        raise RuntimeError('HTTP ' + str(e.code) + '（响应正文隐藏以免泄露凭证）') from None

def gpg(args, data=None):
    r = subprocess.run(['gpg', '--batch', '--quiet'] + args, input=data, capture_output=True, timeout=60)
    if r.returncode:
        raise RuntimeError('GPG 操作失败，请检查密钥及 gpg-agent')
    return r.stdout

def save(path, cfg):
    encrypted = gpg(['--encrypt', '--recipient', cfg['gpg_recipient']], json.dumps(cfg).encode())
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.trello-', suffix='.gpg')
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(encrypted)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)

def exchange(cfg, **payload):
    result = request('https://auth.atlassian.com/oauth/token', 'POST', dict(client_id=cfg['client_id'], client_secret=cfg['client_secret'], **payload))
    if not result.get('access_token') or not result.get('refresh_token'):
        raise RuntimeError('Token 响应不完整，需重新授权')
    cfg.update(access_token=result['access_token'], refresh_token=result['refresh_token'], expires_at=time.time()+float(result['expires_in']))

def resource_id(value):
    if not value or not value.isascii() or not all(c.isalnum() or c in '_-' for c in value):
        raise argparse.ArgumentTypeError('请使用资源 ID，不要使用名称或 URL')
    return value


def add_resource_commands(sub):
    """Declarative command definitions; each leaf builds one API request."""
    def group(name, help):
        return sub.add_parser(name, help=help).add_subparsers(dest='action', required=True)

    def leaf(group, name, method, route, help, fields=(), ids=(), query=None):
        p = group.add_parser(name, help=help)
        p.set_defaults(route=route, method=method, body_fields=dict(fields), query_defaults=query or {})
        for ident in ids:
            p.add_argument(ident, type=resource_id)
        for flag, key in fields:
            p.add_argument('--' + flag.replace('_', '-'), required=(name == 'create' and flag in ('name', 'board', 'list', 'card')) or flag in ('text', 'to_list'), type=resource_id if flag in ('board', 'workspace', 'list', 'card', 'to_list', 'member', 'label') else str)
        if method == 'GET':
            p.add_argument('--fields', help='逗号分隔的返回字段（资源详情/列表）')
        return p

    w = group('workspace', '工作区查询')
    leaf(w, 'list', 'GET', '/members/me/organizations', '列出工作区')
    leaf(w, 'show', 'GET', '/organizations/{id}', '工作区详情', ids=('id',))
    leaf(w, 'boards', 'GET', '/organizations/{id}/boards', '工作区看板', ids=('id',))
    leaf(w, 'members', 'GET', '/organizations/{id}/members', '工作区成员', ids=('id',))

    b = group('board', '看板查询及操作')
    p = leaf(b, 'list', 'GET', '/members/me/boards', '列出看板')
    p.add_argument('--filter', choices=['all', 'open', 'closed'], default='open')
    for action in ('show', 'members', 'labels'):
        leaf(b, action, 'GET', '/boards/{id}' + ('' if action == 'show' else '/' + action), action, ids=('id',))
    for action in ('lists', 'cards'):
        p = leaf(b, action, 'GET', '/boards/{id}/' + action, action, ids=('id',))
        p.add_argument('--filter', choices=['all', 'open', 'closed'], default='open')
    leaf(b, 'create', 'POST', '/boards', '创建看板', fields=(('name','name'),('workspace','idOrganization'),('description','desc')))
    leaf(b, 'update', 'PUT', '/boards/{id}', '修改看板', ids=('id',), fields=(('name','name'),('description','desc')))

    l = group('list', '列表查询及操作')
    leaf(l, 'list', 'GET', '/boards/{board}/lists', '列出看板内列表', ids=('board',), query={'filter':'open'})
    leaf(l, 'show', 'GET', '/lists/{id}', '列表详情', ids=('id',))
    leaf(l, 'cards', 'GET', '/lists/{id}/cards', '列表中的卡片', ids=('id',))
    leaf(l, 'create', 'POST', '/lists', '创建列表', fields=(('board','idBoard'),('name','name'),('position','pos')))
    leaf(l, 'update', 'PUT', '/lists/{id}', '修改列表', ids=('id',), fields=(('name','name'),('position','pos')))

    c = group('card', '卡片查询及操作')
    p = leaf(c, 'list', 'GET', '', '按看板或列表列出卡片')
    parent = p.add_mutually_exclusive_group(required=True)
    parent.add_argument('--board', type=resource_id)
    parent.add_argument('--list', type=resource_id)
    p.add_argument('--filter', choices=['all','open','closed'], default='open')
    for action in ('show', 'comments', 'attachments', 'checklists', 'members'):
        route = '/cards/{id}' + ('' if action == 'show' else '/actions' if action == 'comments' else '/' + action)
        p = leaf(c, action, 'GET', route, action, ids=('id',), query={'filter':'commentCard'} if action == 'comments' else None)
        if action == 'comments':
            p.add_argument('--limit', type=int, choices=range(1,1001), metavar='1..1000', default=50)
            p.add_argument('--before', type=resource_id, help='上一页最后一条 action ID')
    fields = (('name','name'),('description','desc'),('due','due'),('position','pos'))
    leaf(c, 'create', 'POST', '/cards', '创建卡片', fields=(('list','idList'),)+fields)
    p = leaf(c, 'update', 'PUT', '/cards/{id}', '修改卡片；--due null 清除截止时间', ids=('id',), fields=fields)
    p.add_argument('--due-complete', choices=['true','false'])
    leaf(c, 'move', 'PUT', '/cards/{id}', '移动卡片', ids=('id',), fields=(('to_list','idList'),('board','idBoard'),('position','pos')))
    leaf(c, 'comment', 'POST', '/cards/{id}/actions/comments', '添加评论', ids=('id',), fields=(('text','text'),))
    for resource, endpoint in (('member','idMembers'),('label','idLabels')):
        p = leaf(c, 'add-' + resource, 'POST', '/cards/{id}/'+endpoint, '添加'+resource, ids=('id',resource))
        p.set_defaults(value_arg=resource)
        leaf(c, 'remove-' + resource, 'DELETE', '/cards/{id}/'+endpoint+'/{'+resource+'}', '移除'+resource, ids=('id',resource))
    for g, resource in ((b,'boards'),(l,'lists'),(c,'cards')):
        for action in ('archive','unarchive'):
            p = leaf(g, action, 'PUT', '/'+resource+'/{id}', '归档/关闭' if action == 'archive' else '恢复', ids=('id',))
            p.set_defaults(fixed_body={'closed':action == 'archive'})
    leaf(c, 'delete', 'DELETE', '/cards/{id}', '永久删除卡片（不可恢复）', ids=('id',))


def prepare_request(a):
    if a.cmd == 'api':
        return a.method, a.path, json.loads(a.data) if a.data else None
    values = vars(a)
    route = a.route.format(**values)
    if a.cmd == 'card' and a.action == 'list':
        route = '/boards/' + a.board + '/cards' if a.board else '/lists/' + a.list + '/cards'
    query = dict(a.query_defaults)
    for key in ('fields', 'filter', 'limit', 'before'):
        if values.get(key) is not None:
            query[key] = values[key]
    if query:
        route += '?' + urlencode(query)
    body = {key: values[flag] for flag,key in a.body_fields.items() if values.get(flag) is not None}
    body.update(values.get('fixed_body', {}))
    if values.get('value_arg'):
        body['value'] = values[a.value_arg]
    if body.get('due') == 'null':
        body['due'] = None
    if values.get('due_complete') is not None:
        body['dueComplete'] = a.due_complete == 'true'
    if a.action == 'update' and not body:
        raise RuntimeError('请至少指定一个修改字段；使用 --help 查看选项')
    return a.method, route, body or None


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='cmd', required=True)
    sub.add_parser('login')
    sub.add_parser('refresh')
    api = sub.add_parser('api')
    api.add_argument('method', choices=['GET', 'POST', 'PUT', 'DELETE'])
    api.add_argument('path', help='/members/me or /boards/ID/cards')
    api.add_argument('--data', help='JSON request body')
    add_resource_commands(sub)
    a = p.parse_args()
    if a.cmd not in ("login", "refresh"):
        a.method, a.path, request_body = prepare_request(a)
    path = (Path.home() / '.config/agent/auth/trello.json.gpg').resolve()
    if not path.is_file():
        raise RuntimeError('缺少凭证：~/.config/agent/auth/trello.json.gpg；请按技能配置说明创建。')
    lockdir = Path(tempfile.gettempdir()) / ('trello-' + str(os.getuid()))
    lockdir.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = lockdir / hashlib.sha256(str(path).encode()).hexdigest()
    with open(lock, 'a') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        cfg = json.loads(gpg(['--decrypt', str(path)]))
        for k in ('client_id', 'client_secret', 'redirect_uri', 'scopes', 'gpg_recipient'):
            if not cfg.get(k):
                raise RuntimeError('缺少配置字段：' + k)
        # Check encryption works before rotating any token.
        gpg(['--encrypt', '--recipient', cfg['gpg_recipient']], b'check')
        if a.cmd == 'login':
            verifier = secrets.token_urlsafe(48)
            state = secrets.token_urlsafe(32)
            challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
            scopes = cfg['scopes'].split() if isinstance(cfg['scopes'], str) else list(cfg['scopes'])
            scopes = list(dict.fromkeys(scopes + ['offline_access']))
            print('在浏览器打开：\nhttps://auth.atlassian.com/authorize?' + urlencode(dict(client_id=cfg['client_id'], redirect_uri=cfg['redirect_uri'], scope=' '.join(scopes), response_type='code', prompt='consent', state=state, code_challenge=challenge, code_challenge_method='S256')))
            callback = urlsplit(getpass.getpass('授权后粘贴完整回调 URL（隐藏输入）：'))
            expected = urlsplit(cfg['redirect_uri'])
            q = parse_qs(callback.query)
            if (callback.scheme, callback.netloc, callback.path) != (expected.scheme, expected.netloc, expected.path) or q.get('state') != [state] or len(q.get('code', [])) != 1 or 'error' in q:
                raise RuntimeError('回调地址、state 或授权码无效')
            exchange(cfg, grant_type='authorization_code', redirect_uri=cfg['redirect_uri'], code=q['code'][0], code_verifier=verifier)
            save(path, cfg)
            print('授权完成，令牌已加密保存。')
            return
        if a.cmd == 'refresh' or time.time() >= cfg.get('expires_at', 0)-90:
            if not cfg.get('refresh_token'):
                raise RuntimeError('请先执行 login')
            exchange(cfg, grant_type='refresh_token', refresh_token=cfg['refresh_token'])
            save(path, cfg)
        if a.cmd == 'refresh':
            print('刷新完成。')
            return
        u = urlsplit(a.path)
        if u.scheme or u.netloc or u.fragment or not u.path.startswith('/') or '..' in u.path or '\\' in a.path or u.path.startswith('/1/'):
            raise RuntimeError('必须提供 /members/me 这样的相对 API 路径，不含 /1 前缀')
        result = request('https://trello.com/1' + a.path, a.method, request_body, cfg['access_token'])
        print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    try:
        main()
    except (Exception, KeyboardInterrupt) as e:
        print(str(e) if isinstance(e, RuntimeError) else '操作失败（详细异常隐藏）；请检查配置、网络和 GPG。', file=sys.stderr)
        sys.exit(1)
