RAW,USER,HDR=2352,2048,24
def readfile(path,lba,size):
    nsec=(size+USER-1)//USER
    with open(path,"rb") as f:
        f.seek(lba*RAW); raw=f.read(nsec*RAW)
    # join user regions via list comprehension (fast in CPython)
    parts=[raw[s*RAW+HDR:s*RAW+HDR+USER] for s in range(nsec)]
    return b"".join(parts)[:size]
