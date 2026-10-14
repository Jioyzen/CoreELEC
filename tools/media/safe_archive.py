"""Archive validation shared by build-time assembly and first-boot deployment."""
import hashlib
import pathlib
import re
import tarfile
import zipfile

MAX_TOTAL = 2 * 1024**3
TOKEN = re.compile(rb'(?:sk-[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|smb://[^/\s]+:[^/\s]+@)')
TEXT = {'.py','.xml','.json','.po','.txt','.conf','.rules','.sh','.md','.service'}


def sha256(path):
    result = hashlib.sha256()
    with pathlib.Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):result.update(chunk)
    return result.hexdigest()


def safe_path(name):
    path = pathlib.PurePosixPath(name)
    if not name or path.is_absolute() or any(p in ('..','') for p in path.parts) or '\\' in name:
        raise ValueError('Unsafe archive path')
    return path


def check_text(name, data):
    if pathlib.PurePosixPath(name).suffix in TEXT:
        if TOKEN.search(data):raise ValueError('Private credential in '+name)
        if b'/home/zeng/' in data or b'192.168.2.' in data:
            raise ValueError('Development environment in '+name)


def extract_tar(source, destination):
    destination = pathlib.Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(source) as tar:
        members = tar.getmembers()
        names = set();size = 0
        for item in members:
            safe_path(item.name)
            if item.name in names or not (item.isdir() or item.isfile()):
                raise ValueError('Duplicate or special archive entry')
            names.add(item.name);size += item.size
            if size > MAX_TOTAL:raise ValueError('Archive too large')
        for item in members:
            target = destination.joinpath(*safe_path(item.name).parts)
            if item.isdir():target.mkdir(parents=True,exist_ok=True);continue
            target.parent.mkdir(parents=True,exist_ok=True)
            with tar.extractfile(item) as stream, target.open('wb') as output:
                import shutil
                shutil.copyfileobj(stream,output)
            target.chmod(item.mode & 0o777)
            if target.suffix in TEXT:check_text(item.name,target.read_bytes())


def extract_zip(source, destination, addon_id):
    destination = pathlib.Path(destination)
    names=set();size=0
    with zipfile.ZipFile(source) as archive:
        for item in archive.infolist():
            path=safe_path(item.filename)
            if path.parts[0] != addon_id or item.filename in names:
                raise ValueError('Wrong addon ZIP root or duplicate')
            names.add(item.filename);size+=item.file_size
            if size > MAX_TOTAL or ((item.external_attr>>16)&0o170000)==0o120000:
                raise ValueError('ZIP too large or contains symlinks')
        for item in archive.infolist():
            target=destination.joinpath(*safe_path(item.filename).parts)
            if item.is_dir():target.mkdir(parents=True,exist_ok=True);continue
            target.parent.mkdir(parents=True,exist_ok=True)
            with archive.open(item) as stream,target.open('wb') as output:
                import shutil
                shutil.copyfileobj(stream,output)
            target.chmod(0o755 if item.external_attr>>16 & 0o111 else 0o644)
            if target.suffix in TEXT:check_text(item.filename,target.read_bytes())
