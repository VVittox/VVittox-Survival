"""Unity shop formulas. Purchase levels and free upgrades remain independent."""
from .common import clamp

SPECS={
 'PistolDamage':('Pistol','damage',4,None,20,12,'PISTOL DAMAGE'),
 'PistolAttackSpeed':('Pistol','rate',.2,12,25,14,'FIRE RATE'),
 'PistolRange':('Pistol','range',1.25,35,20,12,'PISTOL RANGE'),
 'PistolMultiShot':('Pistol','multi',1,7,65,55,'MULTISHOT'),
 'PistolProjectileSpeed':('Pistol','projectile_speed',.18,4,30,18,'BULLET SPEED'),
 'PistolPierce':('Pistol','pierce',1,6,70,60,'PIERCE'),
 'PistolCrit':('Pistol','crit',.04,.75,45,28,'CRITICAL'),
 'KnifeDamage':('Knife','knife_damage',7,None,25,14,'KNIFE DAMAGE'),
 'KnifeCount':('Knife','knife_count',1,8,70,65,'EXTRA KNIFE'),
 'KnifeAttackSpeed':('Knife','orbit_speed',28,720,30,18,'KNIFE SPEED'),
 'KnifeRange':('Knife','orbit_radius',.14,4,25,16,'KNIFE RADIUS'),
 'KnifeBladeSize':('Knife','blade_radius',.05,1.2,45,30,'BIG BLADE'),
 'AutomaticDamage':('Automatic','damage',2,None,25,15,'RIFLE DAMAGE'),
 'AutomaticRate':('Automatic','rate',.75,24,30,18,'RIFLE FIRE RATE'),
 'AutomaticRange':('Automatic','range',1,35,20,12,'RIFLE RANGE'),
 'AutomaticBulletSpeed':('Automatic','projectile_speed',.15,4,20,12,'RIFLE BULLET SPEED'),
 'AutomaticMultiShot':('Automatic','multi',1,5,75,50,'RIFLE MULTISHOT'),
 'AutomaticPierce':('Automatic','pierce',1,6,60,40,'RIFLE PIERCE'),
 'AutomaticCritical':('Automatic','crit',.03,.75,50,30,'RIFLE CRITICAL'),
}
ALIASES={'BuyDamage':'BuyPistolDamage','BuyAttackSpeed':'BuyPistolAttackSpeed',
         'BuyKnifeOrbitSpeed':'BuyKnifeAttackSpeed','BuyKnifeRadius':'BuyKnifeRange',
         'BuySniperRifle':'BuySniper','BuyAutomaticWeapon':'BuyAutomatic'}
PRICE_FIELDS={'PistolDamage':'pistolDamageBaseCost','PistolAttackSpeed':'pistolSpeedBaseCost','PistolRange':'pistolRangeBaseCost',
              'KnifeDamage':'knifeDamageBaseCost','KnifeAttackSpeed':'knifeSpeedBaseCost','KnifeRange':'knifeRangeBaseCost'}

class Shop:
    def __init__(self,session,properties):self.game=session;self.properties=properties;self.levels={}
    def weapon(self,kind):return self.game.player.weapons.get(kind) if self.game.player else None
    def describe(self,action):
        action=ALIASES.get(action,action);key=action.removeprefix('Buy');p=self.game.player
        owned=False;maxed=False;available=True;price=0;title=key
        if key in ['Pistol','Knife','Automatic','Sniper','MachineGun','Machete']:
            w=self.weapon(key);available=w is not None;owned=bool(w and w.unlocked)
            price=int(self.properties.get({'Pistol':'pistolPrice','Knife':'knifePrice','Automatic':'unlockCost','Sniper':'sniperPrice','MachineGun':'machineGunPrice','Machete':'machetePrice'}[key],
                                          {'Pistol':40,'Knife':60,'Automatic':100,'Sniper':160,'MachineGun':190,'Machete':110}[key]))
            title={'Pistol':'SHOTGUN','Automatic':'AUTOMATIC RIFLE','MachineGun':'MACHINE GUN','Sniper':'SNIPER RIFLE','Knife':'ORBIT KNIFE','Machete':'MACHETE'}[key]
        elif key in SPECS:
            kind,attr,step,cap,base,growth,title=SPECS[key];w=self.weapon(kind)
            available=bool(w and w.unlocked)
            value=abs(getattr(w,attr,0)) if w else 0
            maxed=cap is not None and value>=cap
            base=self.properties.get(PRICE_FIELDS.get(key,''),base)
            price=int(base)+self.levels.get(key,0)*growth
        elif key in ['Regeneration','Lifesteal','ParryCooldown']:
            title,attr,cap,price0={'Regeneration':('REGEN AFTER 4s','regen',3.,45),'Lifesteal':('MELEE LIFESTEAL','lifesteal',.12,65),'ParryCooldown':('PARRY COOLDOWN','parry_cooldown',.65,50)}[key]
            price=price0+self.levels.get(key,0)*30
            maxed=getattr(p,attr)<=cap if key=='ParryCooldown' else getattr(p,attr)>=cap
        elif key in ['MoveSpeed','Health','Heal','DashCooldown']:
            if key=='MoveSpeed':title='MOVE SPEED';price=int(self.properties.get('moveSpeedBaseCost',15))+self.levels.get(key,0)*10;maxed=p.move_speed>=12
            elif key=='Health':title='MAX HEALTH';price=int(self.properties.get('healthBaseCost',20))+self.levels.get(key,0)*12;maxed=p.max_health>=1000
            elif key=='Heal':title='HEAL 35 HP';price=15;maxed=p.dead or p.health>=p.max_health
            else:title='DASH COOLDOWN';price=35+p.dash_level*20;maxed=p.dash_cooldown<=1
        else:
            found=False
            for kind in ['Sniper','MachineGun','Machete']:
                if key.startswith(kind) and key[len(kind):] in ['Damage','Rate','Special']:
                    stat=['Damage','Rate','Special'].index(key[len(kind):]);w=self.weapon(kind)
                    available=bool(w and w.unlocked)
                    level=[w.damage_level,w.rate_level,w.special_level][stat] if w else 0
                    price=[30,40,55][stat]+level*[22,25,35][stat];maxed=level>=[15,10,6][stat]
                    title=kind.upper()+' '+['DAMAGE','RATE','SPECIAL'][stat];found=True;break
            if not found:available=False
        return dict(action=action,key=key,title=title,price=clamp(price,0,2147483647),available=available,owned=owned,maxed=maxed)
    def apply(self,key,free=False):
        p=self.game.player
        if key in ['Pistol','Knife','Automatic','Sniper','MachineGun','Machete']:self.weapon(key).unlock();return
        if key in SPECS:
            kind,attr,step,cap,*_=SPECS[key];w=self.weapon(kind)
            if attr=='orbit_speed':
                value=clamp((-1 if w.orbit_speed<0 else 1)*(abs(w.orbit_speed)+step),-720,720)
            else:value=getattr(w,attr)+step
            if cap is not None and key!='KnifeBladeSize':value=min(cap,value)
            if key=='KnifeBladeSize':value=max(w.blade_radius,min(1.2,value));w.visual_multiplier=clamp(w.visual_multiplier+.05,.25,2.5)
            setattr(w,attr,value)
            if kind=='Knife' and attr in ['knife_count','blade_radius']:w.rebuild_blades()
            return
        if key=='Regeneration':p.regen=min(3.,p.regen+.5)
        elif key=='Lifesteal':p.lifesteal=min(.12,p.lifesteal+.02)
        elif key=='ParryCooldown':p.parry_cooldown=max(.65,p.parry_cooldown-.15)
        elif key=='MoveSpeed':p.move_speed=clamp(p.move_speed+(.30 if free else .35),0,12)
        elif key=='Health':p.upgrade_health(18 if free else 20)
        elif key=='Heal':p.heal(30 if free else 35)
        elif key=='DashCooldown':p.upgrade_dash()
        elif key.startswith('Coins'):p.add_coins({'CoinsSmall':12,'CoinsMedium':18,'CoinsLarge':24}[key])
        else:
            for kind in ['Sniper','MachineGun','Machete']:
                if key.startswith(kind):
                    suffix=key[len(kind):]
                    if suffix in ['Damage','Rate','Special']:self.weapon(kind).arsenal_upgrade(['Damage','Rate','Special'].index(suffix));return
    def buy(self,action):
        if self.game.gameover or self.game.changing_scene:return False
        info=self.describe(action)
        if self.game.is_zombie:
            if not self.game.waves.intermission or 'Shop' not in self.game.pause_reasons:return False
            if info['key'] in ['Pistol','Knife','Automatic','Sniper','MachineGun','Machete']:return False
        if not info['available'] or info['owned'] or info['maxed'] or not self.game.player.spend(info['price']):return False
        self.apply(info['key']);self.levels[info['key']]=self.levels.get(info['key'],0)+1;return True
    def free_choices(self):
        keys=['MoveSpeed','Health','Heal','DashCooldown','Regeneration','Lifesteal','ParryCooldown']+[k for k in SPECS if not k.startswith('Automatic')]
        for kind in ['Sniper','MachineGun','Machete']:keys += [kind+s for s in ['Damage','Rate','Special']]
        keys+=['AutomaticDamage','AutomaticRate','AutomaticPierce']
        available=[k for k in keys if (lambda i:i['available'] and not i['maxed'])(self.describe('Buy'+k))]
        for fallback in ['CoinsSmall','CoinsMedium','CoinsLarge']:
            if len(available)<3:available.append(fallback)
        self.game.rng.shuffle(available);return available[:3]
    def choice_text(self,key):
        descriptions={'Regeneration':'+0.5 HP/sec after 4s without damage','Lifesteal':'+2% health from melee damage','ParryCooldown':'-0.15 sec guard cooldown','MoveSpeed':'+0.30 speed','Health':'+18 max HP','Heal':'Restore 30 HP','DashCooldown':'-0.25 sec',
                      'PistolDamage':'+4 damage','PistolAttackSpeed':'+0.20 shots/sec','PistolRange':'+1.25 range',
                      'PistolMultiShot':'+1 projectile','PistolProjectileSpeed':'+18% projectile speed','PistolPierce':'+1 enemy pierced','PistolCrit':'+4% critical chance',
                      'KnifeDamage':'+7 damage','KnifeCount':'+1 orbiting knife','KnifeAttackSpeed':'+28 orbit speed','KnifeRange':'+0.14 orbit radius','KnifeBladeSize':'+blade hit size',
                      'AutomaticDamage':'+2 damage','AutomaticRate':'+0.75 shots/sec','AutomaticPierce':'+1 pierced enemy',
                      'SniperDamage':'+18 damage','SniperRate':'+0.09 shots/sec','SniperSpecial':'+1 pierce and +1.5 range',
                      'MachineGunDamage':'+2.5 damage','MachineGunRate':'+1 shot/sec','MachineGunSpecial':'Less heat and faster cooling',
                      'MacheteDamage':'+10 damage','MacheteRate':'+0.12 swings/sec','MacheteSpecial':'Wider sweep and stronger knockback',
                      'CoinsSmall':'+12 coins','CoinsMedium':'+18 coins','CoinsLarge':'+24 coins'}
        return self.describe('Buy'+key)['title'] if not key.startswith('Coins') else 'COINS',descriptions.get(key,key)
