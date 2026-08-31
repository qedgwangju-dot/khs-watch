import json, requests
from datetime import datetime
from zoneinfo import ZoneInfo

now=datetime.now(ZoneInfo('Asia/Seoul'))
d=now.strftime('%Y%m%d')
url='https://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd'
headers={
 'User-Agent':'Mozilla/5.0',
 'Referer':'https://data.krx.co.kr/contents/MDC/MDI/outerLoader/index.cmd?screenId=MDCSTAT022',
 'Origin':'https://data.krx.co.kr',
 'X-Requested-With':'XMLHttpRequest',
}
forms=[
 {'bld':'dbms/MDC/STAT/standard/MDCSTAT02202','locale':'ko_KR','inqTpCd':'2','trdVolVal':'2','askBid':'3','mktId':'STK','strtDd':d,'endDd':d,'money':'1','csvxls_isNo':'false'},
 {'bld':'dbms/MDC/STAT/standard/MDCSTAT02202','locale':'ko_KR','inqTpCd':'2','trdVolVal':'2','askBid':'3','mktId':'STK','strtDd':d,'endDd':d,'money':'3','csvxls_isNo':'false'},
]
for i,form in enumerate(forms,1):
 r=requests.post(url,data=form,headers=headers,timeout=30)
 print('FORM',i,'status',r.status_code,'ctype',r.headers.get('content-type'))
 print(r.text[:5000])
