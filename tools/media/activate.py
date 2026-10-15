"""Enable offline-installed addons after Kodi is ready; no remote RPC server."""
import json
import os
import pathlib
import time
import xml.etree.ElementTree as ET
import xbmc

STORAGE=pathlib.Path('/storage')
BUNDLE=pathlib.Path('/usr/share/jioyzen-media')


def rpc(method,params):
    response=json.loads(xbmc.executeJSONRPC(json.dumps({'jsonrpc':'2.0','id':1,'method':method,'params':params})))
    if 'error' in response:raise ValueError('Kodi setup failed: '+method)
    return response['result']


def main():
    marker=STORAGE/'.cache/jioyzen-media/activation.json'
    summary=json.loads((BUNDLE/'profile.json').read_text())
    try:previous=json.loads(marker.read_text())
    except (OSError,ValueError):previous={}
    if previous.get('status')=='complete' and previous.get('profile_id')==summary['profile_id']:return
    try:
        deployment=json.loads((STORAGE/'.cache/jioyzen-media/deployment.json').read_text())
        to_enable=set(summary['addons']) if deployment.get('fresh_settings') else set(deployment.get('new_addons',[]))
        disabled=set(summary.get('default_disabled_addons',[]))
        to_disable=disabled & to_enable
        to_enable-=disabled
        pending=set(summary['addons']);enabled=set()
        # Dependency modules before scripts/skins: every required local
        # component is already present; this loop never invokes an installer.
        for attempt in range(len(pending)+1):
            progressed=False
            for aid in sorted(pending):
                root=ET.parse(STORAGE/'.kodi/addons'/aid/'addon.xml').getroot()
                required={n.get('addon') for n in root.findall('requires/import') if n.get('optional')!='true'}
                if (required & pending)-{aid}:continue
                details=rpc('Addons.GetAddonDetails',{'addonid':aid,'properties':['enabled']})
                if aid in to_enable and not details['addon']['enabled']:
                    if rpc('Addons.SetAddonEnabled',{'addonid':aid,'enabled':True})!='OK':raise ValueError('Enable rejected')
                if aid in to_disable and details['addon']['enabled']:
                    if rpc('Addons.SetAddonEnabled',{'addonid':aid,'enabled':False})!='OK':raise ValueError('Disable rejected')
                if aid in to_enable or (details['addon']['enabled'] and aid not in to_disable):enabled.add(aid)
                pending.remove(aid);progressed=True
            if not pending:break
            if not progressed:raise ValueError('Unresolved addon dependency graph')
        # Fresh installations already received these values before Kodi
        # started. Do not reselect a skin or overwrite settings on upgrades.
        xbmc.executebuiltin('Weather.Refresh')
        if rpc('Settings.GetSettingValue',{'setting':'weather.addon'}).get('value')=='weather.jioyzen':
            xbmc.executebuiltin('RunScript(/storage/.kodi/addons/weather.jioyzen/default.py)')
        report={'status':'complete','profile_id':summary['profile_id'],'addons':sorted(enabled),'disabled_by_default':sorted(disabled),'time':int(time.time())}
    except (OSError,ValueError,KeyError,ET.ParseError) as error:
        report={'status':'failed','profile_id':summary['profile_id'],'error':type(error).__name__}
        xbmc.log('[Jioyzen Media] First-use activation failed: '+str(error),xbmc.LOGERROR)
    marker.parent.mkdir(parents=True,exist_ok=True)
    temporary=marker.with_suffix('.partial');temporary.write_text(json.dumps(report)+'\n');os.replace(temporary,marker)


if __name__=='__main__':main()
