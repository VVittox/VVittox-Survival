from __future__ import annotations
import json
import math
import random
from pathlib import Path
from engine.scene import Node, UILabel, Sprite2D
from engine.scene.ui_nodes import UIButton, UIImage, VideoPlayer
from engine.scene.serialization import load_prefab,node_to_dict,node_from_dict
from engine.scripting import attach_project_scripts,connect_scene_signals
from engine.utils.vmath import Vector2
from .common import *
from .profile import Profile
from .shop import Shop
from .content import RunContent,WEAPONS,FINISHES,HATS,DIFFICULTIES

class Session:
    def __init__(self,director):
        self.director=director;self.profile=Profile();self.rng=random.Random();self.fx_rng=random.Random()
        self.player=None;self.waves=None;self.camera=None;self.joystick=None
        self.enemies=[];self.time=0.0;self.unscaled=0.0;self.run_seconds=0.0;self.kills=0
        self.pause_reasons=set();self.gameover=False;self.changing_scene=False
        self.roles={};self.templates={};self.pools={};self.active_projectiles=0;self.serial=0
        self.mode=self.director.properties.get('mode','Game');self.choices=[];self.accept_after=0
        self.ui_focus=0;self.focus_panel='';self.touch_seen=False;self.health_fill=1;self.wave_fill=0;self.warning=self.profile.warning
        self.content=RunContent(self);self.selected_weapon=0
        self.shop_page=0;self.shop=None;self.last_ui_update=-100
        self.is_zombie=self.director.properties.get('survival_mode','Classic')=='Zombie'
        self.zombies=None
    @property
    def engine(self):return self.director.engine
    @property
    def scene(self):return self.director.owner
    @property
    def paused(self):return bool(self.pause_reasons)
    def ready(self):
        for node in self.scene.walk():
            role=node.script_properties.get('role')
            if role:self.roles[role]=node
            if isinstance(node,UIButton):
                action=node.script_properties.get('action','')
                if action:node.signals.connect('pressed',lambda a=action,n=node:self.action(a,n))
        for n in self.scene.walk():
            if n._script_instance is None:
                if type(n)._process is Node._process:n.set_process(False)
                if type(n)._physics_process is Node._physics_process:n.set_physics_process(False)
        self.ui_buttons=[n for n in self.scene.walk() if isinstance(n,UIButton)]
        self.shop_buttons=[n for n in self.ui_buttons if n.script_properties.get('action','').startswith('Buy')]
        self.render_nodes=[n for n in self.scene.walk() if isinstance(n,(Sprite2D,UIImage,VideoPlayer))]
        self.video_nodes=[n for n in self.render_nodes if isinstance(n,VideoPlayer)]
        self.focused_button=None;self.applied_quality=None
        self.projectile_counts={False:0,True:0}
        self.profile.apply(self.engine,display=True)
        self.engine.events.on('engine_stopping',self.on_stopping)
        if self.mode=='Game':
            self.enemy_root=self.scene.find_child('Enemies');self.projectile_root=self.scene.find_child('Projectiles')
            if self.player is None or self.waves is None:raise RuntimeError('Player and WaveSystem scripts are required')
            self.content.apply_loadout();self.content.cosmetics(force=True)
            if self.is_zombie:
                from .zombies import ZombieWorld
                self.zombies=ZombieWorld(self)
            self.shop=Shop(self,self.director.properties.get('shop',{}))
            for role in ['pause','gameover','upgrade','shop','shop_extra','settings','skins']:self.show(role,False)
            self.engine.physics.settings.time_scale=1
            self.engine.physics.rebuild_queries_2d(self.engine.tree.root)
        elif self.mode=='Menu':self.show_main()
        self.update_ui(.016,force=True)
    def on_stopping(self,*args):self.profile.flush()
    def exit(self):
        self.changing_scene=True;self.profile.flush()
        if self.zombies:self.zombies.box.cancel(refund=False);self.waves.stop()
        self.engine.physics.settings.time_scale=1
        self.engine.events.off('engine_stopping',self.on_stopping)
        self.pools.clear();self.templates.clear()
    def show(self,role,visible):
        node=self.roles.get(role)
        if node is None or node.visible==bool(visible):return
        node.visible=bool(visible)
        for button in node.walk():
            if isinstance(button,UIButton):
                button._held.clear();button._hovered=False;button.focused=False
        self.focus_panel=''
    def visible(self,role):
        node=self.roles.get(role)
        return node is not None and node.is_visible_in_tree
    def pause(self,reason):self.pause_reasons.add(reason);self.engine.physics.settings.time_scale=0
    def resume(self,reason):
        self.pause_reasons.discard(reason);self.engine.physics.settings.time_scale=0 if self.paused else 1
    def toggle_pause(self):
        if self.gameover:return
        if 'PauseMenu' in self.pause_reasons:
            for role in ['pause','settings','skins']:self.show(role,False)
            self.resume('PauseMenu')
        elif not self.paused:self.show('pause',True);self.pause('PauseMenu')
    def toggle_shop(self):
        if self.is_zombie:
            if 'Shop' in self.pause_reasons:self.close_shop()
            elif not self.paused and not self.gameover and self.waves.intermission:
                self.shop_page=0;self.show('shop_extra',True);self.pause('Shop');self.refresh_extra_shop()
            else:self.content.notify('UPGRADES: BETWEEN WAVES ONLY')
            return
        if 'Shop' in self.pause_reasons:self.close_shop()
        elif not self.paused and not self.gameover:
            self.shop_page=0;self.show('shop',True);self.show('shop_extra',False);self.pause('Shop')
    def close_shop(self):self.show('shop',False);self.show('shop_extra',False);self.resume('Shop')
    def show_upgrades(self):
        if self.is_zombie and (not self.waves.intermission or self.gameover or self.changing_scene):return
        self.choices=self.shop.free_choices();self.accept_after=self.unscaled+.15
        self.show('upgrade',True);self.pause('Upgrade')
        for i,key in enumerate(self.choices):
            title,description=self.shop.choice_text(key)
            self.set_text(f'upgrade_title_{i}',title);self.set_text(f'upgrade_desc_{i}',description)
    def choose_upgrade(self,index):
        if 'Upgrade' not in self.pause_reasons or self.gameover or self.unscaled<self.accept_after or not 0<=index<len(self.choices):return False
        if self.is_zombie and not self.waves.intermission:return False
        self.shop.apply(self.choices[index],free=True)
        self.show('upgrade',False);self.resume('Upgrade');self.choices=[];return True
    def game_over(self):
        if self.gameover:return
        self.gameover=True;self.pause_reasons.clear();self.pause('GameOver')
        if self.zombies:self.zombies.box.cancel(refund=False);self.waves.stop()
        for role in ['pause','upgrade','shop','shop_extra']:self.show(role,False)
        self.show('gameover',True);self.profile.flush();self.update_ui(.016,force=True)
    def change_scene(self,name):
        if self.changing_scene:return
        self.changing_scene=True;self.profile.flush();self.pause_reasons.clear();self.engine.physics.settings.time_scale=1
        self.engine.change_scene('scenes/'+name+'.vscene')
    def show_main(self):
        self.show('settings',False);self.show('skins',False);self.show('mode_select',False)
        if self.mode=='Game':
            if not self.gameover:self.show('pause',True);self.pause('PauseMenu')
            return
        self.show('main',True);self.menu_chrome(True)

    def open_options(self,role):
        if self.mode=='Game':
            if self.gameover or self.pause_reasons-{'PauseMenu'}:return
            self.pause('PauseMenu')
        for key in ['pause','main','settings','skins']:self.show(key,False)
        self.show(role,True);self.menu_chrome(False)

    def refresh_menu_video(self):
        if self.mode!='Menu':return
        if not hasattr(self,'_original_ui_videos'):
            self._original_ui_videos=[n for n in self.scene.walk() if isinstance(n,VideoPlayer)]
        enabled=bool(self.profile.get('Settings.MenuVideo',1))
        for video in self._original_ui_videos:
            video.visible=enabled;video.autoplay=enabled
            if not enabled and video.playing:video.stop()
    def menu_chrome(self,visible):
        for node in self.scene.walk():
            if node.is_in_group('menu_chrome'):node.visible=bool(visible)
    def action(self,action,node=None):
        if self.changing_scene:return
        if self.is_zombie and action in ['ShopExtra','ShopBack','ShopNext','ShopPrevious'] and (not self.waves.intermission or self.gameover):return
        if action.startswith('Buy'):
            if self.shop:self.shop.buy(action)
        elif action=='StartGame':
            self.show('main',False);self.show('mode_select',True);self.menu_chrome(False)
        elif action=='StartClassic':self.change_scene('Game')
        elif action=='StartZombie':self.change_scene('Zombie')
        elif action=='InteractBox' and self.zombies:self.zombies.box.buy()
        elif action in ['ReturnToMenu','LoadMenu']:self.change_scene('Menu')
        elif action=='RestartGame':self.change_scene('Zombie' if self.is_zombie else 'Game')
        elif action in ['QuitGame','QuitApplication']:self.profile.flush();self.engine.stop()
        elif action=='ShowMain':self.show_main()
        elif action=='ShowSettings':self.open_options('settings')
        elif action=='ShowSkins':self.open_options('skins')
        elif action in ['Pause','TogglePause']:self.toggle_pause()
        elif action=='Resume':
            for role in ['pause','settings','skins']:self.show(role,False)
            self.resume('PauseMenu')
        elif action in ['OpenShop','ToggleShop']:self.toggle_shop()
        elif action=='CloseShop':self.close_shop()
        elif action=='Dash' and self.player:self.player.try_dash()
        elif action.startswith('Upgrade'):self.choose_upgrade(int(action[-1]))
        elif action.startswith('SelectSkin'):
            self.profile.set('Save.SelectedSkin',clamp(int(action[-1]),0,5));self.profile.flush()
        elif action=='Parry' and self.player:self.player.try_parry()
        elif action.startswith('Cosmetic:'):self.cosmetic_action(action[9:])
        elif action.startswith('Setting:'):self.setting(action[8:])
        elif action=='ShopExtra':self.shop_page=0;self.show('shop',False);self.show('shop_extra',True);self.refresh_extra_shop()
        elif action=='ShopBack':
            if self.is_zombie:self.close_shop()
            else:self.show('shop_extra',False);self.show('shop',True)
        elif action=='ShopNext':self.shop_page+=1;self.refresh_extra_shop()
        elif action=='ShopPrevious':self.shop_page=max(0,self.shop_page-1);self.refresh_extra_shop()
        elif action.startswith('ExtraBuy'):
            index=int(action.removeprefix('ExtraBuy'));items=self.extra_items()
            if self.shop and index+self.shop_page*8<len(items):self.shop.buy(items[index+self.shop_page*8])
            self.refresh_extra_shop()
        elif action=='OpenLink' and node is not None:
            import webbrowser
            url=str(node.script_properties.get('url',''))
            if url.startswith(('https://','http://')):webbrowser.open(url)
        self.update_ui(.016,force=True)
    def setting(self,key):
        p=self.profile;display=False
        if key in ['VSync','Fullscreen','CameraShake','ShowFPS','TouchControls','MenuVideo','SFXPitch','Diagnostics']:
            p.set('Settings.'+key,0 if p.get('Settings.'+key,0) else 1);display=key in ['VSync','Fullscreen']
        elif key=='TargetFPS':
            values=[30,45,60,90,120,144,165,240,-1];value=p.get('Settings.TargetFPS',60)
            p.set('Settings.TargetFPS',values[(values.index(value)+1)%len(values)] if value in values else 60)
        elif key=='Resolution':
            values=[(800,450),(1024,576),(1280,720),(1600,900),(1920,1080),(2560,1440)]
            current=(int(self.engine.renderer.size.x),int(self.engine.renderer.size.y)) if self.engine.renderer else (1280,720)
            selected=values[(values.index(current)+1)%len(values)] if current in values else (1280,720)
            p.set('Settings.ResolutionWidth',selected[0]);p.set('Settings.ResolutionHeight',selected[1]);display=True
        elif key in ['VolumeUp','VolumeDown']:
            p.set('Settings.MasterVolume',round(clamp(p.get('Settings.MasterVolume',1)+(.1 if key=='VolumeUp' else -.1),0,1),2))
        elif key=='Quality':p.set('Settings.Quality',(p.get('Settings.Quality',1)+1)%3)
        elif key in ['Difficulty','RenderScale','Zoom','ShakeStrength','HUDScale','Loadout']:
            catalogs={'Difficulty':[0,1,2],'RenderScale':[.5,.67,.75,.85,1.],
                      'Zoom':[.8,1.,1.15,1.3],'ShakeStrength':[0.,.35,.7,1.],
                      'HUDScale':[.85,1.,1.15],'Loadout':[0,1,2]}
            dest='Save.Loadout' if key=='Loadout' else 'Settings.'+key
            values=catalogs[key];old=p.get(dest);p.set(dest,values[(values.index(old)+1)%len(values)] if old in values else values[0])
        elif key=='Defaults':
            from .profile import DEFAULTS
            for k,v in DEFAULTS.items():
                if k.startswith('Settings.'):p.set(k,v)
            p.set('Settings.ResolutionWidth',1280);p.set('Settings.ResolutionHeight',720);display=True
        p.apply(self.engine,display);p.flush()
    def physics(self,dt):
        if self.mode=='Game' and not self.paused and not self.gameover and not self.changing_scene:
            self.time+=dt;self.run_seconds+=dt;self.content.update(dt)
            if self.zombies:self.zombies.update(dt)
    def process(self,dt):
        self.unscaled+=dt
        if self.mode=='Start':
            if self.unscaled>=float(self.director.properties.get('delay',6)):self.change_scene('Menu')
            return
        inp=self.engine.input
        if inp is not None:
            if inp.touches:self.touch_seen=True
            cancel=inp.action_just_pressed('ui_cancel') or 1 in inp.pad_pressed
            if inp.action_just_pressed('performance_report'):self.export_performance()
            if self.mode=='Game':
                if inp.focus_lost and not self.paused and not self.gameover:self.toggle_pause();self.profile.flush()
                if self.zombies and (inp.action_just_pressed('interact') or 2 in inp.pad_pressed):self.zombies.box.buy()
                if inp.action_just_pressed('shop'):self.toggle_shop()
                if cancel:
                    if self.visible('settings') or self.visible('skins'):self.show_main()
                    elif 'Shop' in self.pause_reasons:self.close_shop()
                    elif 'Upgrade' not in self.pause_reasons:self.toggle_pause()
                elif 7 in inp.pad_pressed:self.toggle_pause()
                if 'Upgrade' in self.pause_reasons:
                    for index,name in enumerate(['upgrade_1','upgrade_2','upgrade_3']):
                        if inp.action_just_pressed(name):self.choose_upgrade(index);break
            elif cancel:self.show_main()
            self.navigate(inp)
        touch=bool(self.profile.get('Settings.TouchControls',0) or self.touch_seen)
        self.show('mobile_controls',touch)
        self.update_ui(dt)
    def navigate(self,inp):
        panel=None
        for role in ['settings','skins','upgrade','gameover','pause','shop_extra','shop','mode_select','main']:
            if self.visible(role):panel=self.roles[role];break
        if panel is None:return
        buttons=[n for n in panel.walk() if isinstance(n,UIButton) and n.is_visible_in_tree and not n.disabled and n.script_properties.get('action')]
        if not buttons:return
        if panel.name!=self.focus_panel:
            self.ui_focus=next((i for i,b in enumerate(buttons) if b.script_properties.get('action')=='Resume'),0)
            self.focus_panel=panel.name
        if inp.action_just_pressed('ui_down') or inp.action_just_pressed('ui_right') or 12 in inp.pad_pressed:self.ui_focus+=1
        if inp.action_just_pressed('ui_up') or inp.action_just_pressed('ui_left') or 11 in inp.pad_pressed:self.ui_focus-=1
        self.ui_focus%=len(buttons)
        if self.focused_button is not None:self.focused_button.focused=False
        self.focused_button=buttons[self.ui_focus]
        buttons[self.ui_focus].focused=True
        if inp.action_just_pressed('ui_accept') or 0 in inp.pad_pressed:buttons[self.ui_focus].signals.emit('pressed')
    def set_text(self,role,text):
        node=self.roles.get(role)
        if node is not None and hasattr(node,'text'):node.text=str(text)
    def update_ui(self,dt,force=False):
        if not force and self.unscaled-self.last_ui_update<.05:return
        elapsed=max(dt,self.unscaled-self.last_ui_update) if self.last_ui_update>=0 else dt
        self.last_ui_update=self.unscaled
        self.set_text('best_wave',f"BEST WAVE: {self.profile.get('Save.ZombieBestWave' if self.is_zombie else 'Save.BestWave')}")
        self.show('fps',bool(self.profile.get('Settings.ShowFPS',1)))
        self.set_text('fps',f'FPS: {self.engine.fps:.0f}  {1000/self.engine.fps:.1f} ms' if self.engine.fps>0 else 'FPS: --')
        p=self.player;w=self.waves
        if p is not None:
            self.set_text('coins_text',f'COINS:\n{p.coins}')
            self.set_text('health_text',f'HP: {math.ceil(p.health)} / {math.ceil(p.max_health)}')
            self.health_fill+=clamp(p.health/max(1,p.max_health)-self.health_fill,-elapsed*4,elapsed*4)
            fill=self.roles.get('health_fill')
            if fill is not None:fill.fill_amount=self.health_fill
            self.set_text('dash_label','DASH' if self.time>=p.next_dash else f'{p.next_dash-self.time:.1f}')
            if self.shop and (self.visible('shop') or self.visible('shop_extra')):
                for node in self.shop_buttons:
                    action=node.script_properties.get('action','')
                    if isinstance(node,UIButton) and action.startswith('Buy'):
                        info=self.shop.describe(action);node.disabled=info['owned'] or info['maxed'] or not info['available'] or p.coins<info['price']
                        label=node.find_child('Price')
                        if label:label.text='OWNED' if info['owned'] else 'MAX' if info['maxed'] else str(info['price'])+'*'
            self.set_text('result_text',f"WAVE: {w.current if w else 0}\nCOINS: {p.coins}\nBEST: {self.profile.get('Save.ZombieBestWave' if self.is_zombie else 'Save.BestWave')}\nLIFETIME KILLS: {self.profile.get('Save.ZombieKills' if self.is_zombie else 'Save.LifetimeKills')}")
        if w is not None:
            self.set_text('wave_text',f'Wave: {w.current}');self.set_text('enemies_text',f'Enemies: {w.alive}'+(f' (+{w.pending})' if self.is_zombie else ''))
            target=1-(w.alive+(w.pending if self.is_zombie else 0))/max(1,w.spawn_total) if w.current else 0
            self.wave_fill+=clamp(target-self.wave_fill,-elapsed*3,elapsed*3)
            fill=self.roles.get('wave_fill')
            if fill is not None:fill.fill_amount=self.wave_fill
            if w.error:self.set_text('enemies_text',w.error)
        self.refresh_setting_labels()
        self.refresh_menu_video()
        self.content.hud()
        if self.zombies:self.zombies.hud()
        self.refresh_cosmetics_ui()
        if self.visible('shop_extra'):self.refresh_extra_shop()
        for i,name in enumerate(SKIN_NAMES):
            self.set_text(f'skin_{i}',name+('  [SELECTED]' if self.profile.get('Save.SelectedSkin')==i else ''))
    def refresh_setting_labels(self):
        p=self.profile
        for key in ['VSync','Fullscreen','CameraShake','ShowFPS','TouchControls','MenuVideo','SFXPitch','Diagnostics']:
            self.set_text('setting_'+key,key.upper()+': '+('ON' if p.get('Settings.'+key,1 if key in ['VSync','CameraShake','ShowFPS'] else 0) else 'OFF'))
        import os
        if os.environ.get('VVITTOX_FORCE_WINDOWED'):self.set_text('setting_Fullscreen','FULLSCREEN: OFF (--windowed)')
        fps=p.get('Settings.TargetFPS',60);self.set_text('setting_TargetFPS','FPS LIMIT: '+(str(fps) if fps>0 else 'UNLIMITED'))
        if self.engine.renderer:self.set_text('setting_Resolution',f'RESOLUTION: {int(self.engine.renderer.size.x)} x {int(self.engine.renderer.size.y)}')
        self.set_text('setting_Volume',f"MASTER VOLUME: {round(p.get('Settings.MasterVolume',1)*100)}%")
        self.set_text('setting_Quality','RENDER: '+['LOW','PIXEL','SMOOTH'][int(p.get('Settings.Quality',1))%3])
        self.set_text('setting_Difficulty','DIFFICULTY: '+DIFFICULTIES[int(p.get('Settings.Difficulty',1))])
        self.set_text('setting_RenderScale',f"WORLD RESOLUTION: {round(p.get('Settings.RenderScale',.75)*100)}%")
        self.set_text('setting_Loadout','STARTER: '+['Survivor','Duelist','Ranger'][int(p.get('Save.Loadout',1))])
        for key in ['Zoom','ShakeStrength','HUDScale']:self.set_text('setting_'+key,key.upper()+f": {round(p.get('Settings.'+key,1)*100)}%")
        for node in self.video_nodes:
            if self.mode=='Menu':
                enabled=bool(p.get('Settings.MenuVideo',1))
                node.visible=enabled
                if enabled and not node.playing:node.autoplay=True
                elif not enabled:node.autoplay=False;node.stop()
        for role in ['parry_status','run_modifier','combo_status','health_text','coins_text','wave_text','enemies_text','fps']:
            node=self.roles.get(role)
            if node is not None and hasattr(node,'font_size'):
                if not hasattr(node,'_authored_font_size'):node._authored_font_size=node.font_size
                node.font_size=round(node._authored_font_size*float(p.get('Settings.HUDScale',1.)))
        self.set_text('diagnostics',f"CPU physics {self.engine.profiler.avg('physics'):.1f} / update {self.engine.profiler.avg('process'):.1f} / draw {self.engine.profiler.avg('draw'):.1f} ms | shots {self.active_projectiles}")
        self.show('diagnostics',bool(p.get('Settings.Diagnostics',0)))
        quality=int(p.get('Settings.Quality',1))
        if quality!=self.applied_quality:
            self.applied_quality=quality
            for node in self.scene.walk():
                if isinstance(node,VideoPlayer):node.frame_stride=2 if quality==0 else 1
                if isinstance(node,(Sprite2D,UIImage)):node.pixel_perfect=quality!=2
    def extra_items(self):
        from .shop import SPECS
        return ['Buy'+k for k in SPECS]+['BuyMoveSpeed','BuyHealth','BuyHeal','BuyDashCooldown','BuyRegeneration','BuyLifesteal','BuyParryCooldown']+['Buy'+k+s for k in ['Sniper','MachineGun','Machete'] for s in ['Damage','Rate','Special']]
    def refresh_extra_shop(self):
        if self.shop is None:return
        items=self.extra_items();pages=max(1,math.ceil(len(items)/8));self.shop_page%=pages
        self.set_text('extra_page',f'UPGRADES  {self.shop_page+1} / {pages}')
        for i in range(8):
            node=self.roles.get(f'extra_buy_{i}');index=self.shop_page*8+i
            if node is None:continue
            node.visible=index<len(items)
            if index<len(items):
                info=self.shop.describe(items[index]);node.text=info['title']+'\n'+('MAX' if info['maxed'] else str(info['price'])+' COINS')
                node.disabled=not info['available'] or info['maxed'] or self.player.coins<info['price']
    def record_wave(self,wave):
        if self.is_zombie:self.profile.set('Save.ZombieBestWave',max(self.profile.get('Save.ZombieBestWave'),int(wave)))
        else:self.profile.record_wave(wave)
    def record_kill(self):
        if self.is_zombie:self.profile.set('Save.ZombieKills',min(2147483647,self.profile.get('Save.ZombieKills')+1))
        else:self.profile.add_kill()
    def line_of_sight(self,start,end):
        return self.engine.physics.raycast_2d(self.engine.tree.root,start,end,collision_mask=WORLD) is None
    def shake(self,amount):
        if self.camera:self.camera.trauma=clamp(self.camera.trauma+max(0,amount),0,1)
    def sound(self,profile,event):
        if not profile or self.engine.audio is None:return
        path=profile.get(event+'Sound')
        if path:
            try:self.engine.audio.play(str(self.engine.project_root/path),volume=float(profile.get(event+'Volume',.8 if event=='attack' else .7)),
                                      pitch=self.fx_rng.uniform(float(profile.get('minPitch',.96)),float(profile.get('maxPitch',1.04))) if self.profile.get('Settings.SFXPitch',0) else 1.)
            except (OSError,ValueError) as exc:self.warning=str(exc)
    def instantiate(self,path,parent):
        if path not in self.templates:self.templates[path]=node_to_dict(load_prefab(self.engine.project_root/path))
        node=node_from_dict(self.templates[path]);self.serial+=1;node.name+=f'_{self.serial}'
        attach_project_scripts(node,self.engine.project_root,strict=True);connect_scene_signals(node,strict=True)
        parent.add_child(node)
        for n in node.walk():
            if isinstance(n,Sprite2D):
                n.pixel_perfect=int(self.profile.get('Settings.Quality',1))!=2
                if n._script_instance is None:n.set_process(False);n.set_physics_process(False)
        return node
    def fire(self,path,origin,direction,damage,speed=1,pierce=0,crit=0,crit_mult=2,sfx=None,enemy=False):
        cap=256 if enemy else 1024
        count=self.projectile_counts[bool(enemy)]
        if count>=cap:return False
        pool=self.pools.setdefault(path,[])
        if pool:
            node=pool.pop();self.projectile_root.add_child(node)
        else:node=self.instantiate(path,self.projectile_root)
        node._script_instance.activate(origin,direction,damage,speed,pierce,crit,crit_mult,sfx,enemy,path)
        self.active_projectiles+=1;self.projectile_counts[bool(enemy)]+=1;return True
    def fire_enemy(self,origin,direction,damage):
        return self.fire('prefabs/EnemyProjectile.vprefab',origin,direction,damage,enemy=True)
    def recycle_projectile(self,path,node):
        self.active_projectiles=max(0,self.active_projectiles-1)
        enemy=bool(node._script_instance.enemy);self.projectile_counts[enemy]=max(0,self.projectile_counts[enemy]-1)
        self.pools.setdefault(path,[]).append(node)

    def cosmetic_action(self,key):
        p=self.profile
        if key.startswith('Hat') and key[3:].isdigit():p.set('Save.Hat',int(key[3:])%len(HATS))
        elif key=='Weapon':self.selected_weapon=(self.selected_weapon+1)%len(WEAPONS)
        elif key=='Finish':
            dest='Save.WeaponSkin.'+WEAPONS[self.selected_weapon];p.set(dest,(int(p.get(dest,0))+1)%len(FINISHES))
        elif key=='Hat':p.set('Save.Hat',(int(p.get('Save.Hat',0))+1)%len(HATS))
        elif key=='HatScale':p.set('Save.HatScale',.7 if p.get('Save.HatScale',1.)>=1.39 else round(p.get('Save.HatScale',1.)+.1,1))
        elif key=='HatOffset':p.set('Save.HatOffset',-12 if p.get('Save.HatOffset',0)>=12 else p.get('Save.HatOffset',0)+4)
        self.content.cosmetics(force=True);p.flush()
    def refresh_cosmetics_ui(self):
        p=self.profile;kind=WEAPONS[self.selected_weapon]
        self.set_text('cosmetic_weapon','WEAPON: '+kind.upper())
        self.set_text('cosmetic_finish','FINISH: '+FINISHES[int(p.get('Save.WeaponSkin.'+kind,0))])
        self.set_text('cosmetic_hat','HAT: '+HATS[int(p.get('Save.Hat',0))][0])
        self.set_text('cosmetic_hatscale',f"HAT SIZE: {p.get('Save.HatScale',1.):.1f}x")
        self.set_text('cosmetic_hatoffset',f"HAT HEIGHT: {p.get('Save.HatOffset',0):+d}")
        preview=self.roles.get('cosmetic_hat_preview')
        if preview:preview.texture_path=HATS[int(p.get('Save.Hat',0))][1]
        preview=self.roles.get('cosmetic_weapon_preview')
        if preview:
            from .content import FINISH_TINTS
            preview.color=FINISH_TINTS[int(p.get('Save.WeaponSkin.'+kind,0))]
            preview.texture_path=self.director.properties.get('weaponPreviews',{}).get(kind,'')
        preview=self.roles.get('cosmetic_player_preview')
        if preview:preview.color=SKIN_TINTS[int(p.get('Save.SelectedSkin'))]

    def export_performance(self):
        from datetime import datetime,timezone
        r=self.engine.renderer
        report={'recorded_utc':datetime.now(timezone.utc).isoformat(),'scene':self.scene.name,
                'displayed_fps':self.engine.fps,'average_ms':self.engine.profiler.snapshot(),
                'world_render_scale':self.profile.get('Settings.RenderScale',.75),
                'window_size':[int(r.size.x),int(r.size.y)] if r else None,
                'physics':dict(self.engine.physics.stats),'projectiles':self.active_projectiles,
                'enemies':len(self.enemies),'nodes':sum(1 for _ in self.scene.walk())}
        path=self.engine.project_root.parent/'logs/performance.json'
        try:path.parent.mkdir(exist_ok=True);path.write_text(json.dumps(report,indent=2));self.content.notify('PERFORMANCE REPORT SAVED')
        except OSError as exc:self.warning=str(exc)
