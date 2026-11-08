"""Zombie-only world rules. All objects are authored in Zombie.vscene."""
from __future__ import annotations
import heapq
import math
from engine.physics import PhysicsBody2D
from engine.utils.vmath import Vector2
from .common import WORLD, PLAYER, ENEMY, PPU

BARRICADE = 32

class Barricade:
    def __init__(self, game, node):
        self.game, self.node = game, node
        self.visual = node.find_child('Visual')
        self.properties = node.script_properties
        self.maximum = max(1., float(self.properties.get('health', 120)))
        self.destroy_count = 0
        self.restore()

    @property
    def broken(self):
        return self.health <= 0

    def restore(self):
        self.health = self.maximum
        self.node.collider.enabled = True
        self.visual.texture_path = self.properties['intact_texture']

    def hit(self, damage):
        if self.broken or self.game.paused or self.game.gameover or self.game.changing_scene:
            return False
        if not math.isfinite(damage) or damage <= 0:
            return False
        self.health = max(0., self.health - damage)
        if self.broken:
            self.destroy_count += 1
            self.node.collider.enabled = False
            self.visual.texture_path = self.properties['broken_texture']
            self.game.engine.physics.rebuild_queries_2d(self.game.engine.tree.root)
        return True

class Navigator:
    """Small cached cardinal grid; swept engine queries prevent corner clipping."""
    def __init__(self, game, properties):
        self.game = game
        self.step = max(16., float(properties.get('navigation_step', 24)))
        self.bounds = properties.get('navigation_bounds', [-440, -380, 520, 360])
        self.cells = {}
        x0, y0, x1, y1 = self.bounds
        # Only WORLD bodies participate: the gate has its own collision layer.
        rects = [n.collider.bounds(n.global_position) for n in game.scene.walk()
                 if isinstance(n, PhysicsBody2D) and n.collider.enabled and n.collision_layer & WORLD]
        for ix in range(int((x1-x0)/self.step)+1):
            for iy in range(int((y1-y0)/self.step)+1):
                x, y = x0+ix*self.step, y0+iy*self.step
                if not any(a-24 <= x <= c+24 and b-24 <= y <= d+24 for a,b,c,d in rects):
                    self.cells[ix,iy] = Vector2(x,y)

    def clear(self, start, end):
        return self.game.engine.physics.raycast_2d(self.game.engine.tree.root, start, end,
                                                  collision_mask=WORLD, radius=23) is None

    def nearest(self, point):
        candidates = sorted(self.cells, key=lambda k:(self.cells[k]-point).length)
        return next((k for k in candidates[:12] if self.clear(point,self.cells[k])), None)

    def route(self, start, end):
        a, b = self.nearest(start), self.nearest(end)
        if a is None or b is None:
            return []
        queue = [(0,a)]; cost = {a:0}; previous = {}
        while queue:
            _, cell = heapq.heappop(queue)
            if cell == b:
                result = [end]
                while cell != a:
                    result.append(self.cells[cell]);cell = previous[cell]
                result.append(self.cells[a])
                return result[::-1]
            x,y = cell
            for neighbor in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                if neighbor not in self.cells:
                    continue
                new = cost[cell]+1
                if new < cost.get(neighbor, float('inf')):
                    cost[neighbor] = new;previous[neighbor] = cell
                    heapq.heappush(queue,(new+abs(neighbor[0]-b[0])+abs(neighbor[1]-b[1]),neighbor))
        return []

class MysteryBox:
    def __init__(self, world, node):
        self.world, self.game, self.node = world, world.game, node
        self.visual = node.find_child('Visual')
        self.properties = node.script_properties
        self.price = max(1,int(self.properties.get('price',60)))
        self.state = 'Ready'; self.remaining = 0.; self.reward = None; self.paid = 0
        self.visual.texture_path = self.properties['closed_texture']

    def near(self):
        return (self.game.player.owner.global_position-self.node.global_position).length <= max(32.,float(self.properties.get('interaction_radius',115)))

    def catalog(self):
        entries = []
        for item in self.properties.get('weapons',[]):
            kind, weight = item.get('id'), float(item.get('weight',0))
            w = self.game.player.weapons.get(kind)
            if w is None or weight <= 0 or not math.isfinite(weight):
                continue
            # Validate referenced resources before taking payment.
            projectile = w.properties.get('projectile_prefab','')
            paths = [projectile] if projectile else []
            for n in w.owner.walk():
                texture = getattr(n,'texture_path','')
                if texture:paths.append(texture)
            if all((self.game.engine.project_root/p).is_file() for p in paths):
                entries.append((kind,weight))
        # A roll always changes the active weapon; a one-entry table is refused.
        return [(kind,weight) for kind,weight in entries if kind != self.world.active_weapon]

    def buy(self):
        g = self.game
        if self.state != 'Ready' or g.paused or g.gameover or g.changing_scene or not self.near():
            return False
        if not self.properties.get('during_wave',True) and not self.world.waves.intermission:
            g.content.notify('BOX: BETWEEN WAVES ONLY');return False
        entries = self.catalog()
        if not entries:
            g.content.notify('BOX: NO ALTERNATIVE WEAPON AVAILABLE');return False
        if not g.player.spend(self.price):
            g.content.notify('NOT ENOUGH COINS');return False
        self.paid = self.price
        self.reward = g.rng.choices([k for k,w in entries],[w for k,w in entries])[0]
        self.state = 'Rolling';self.remaining = max(.2,float(self.properties.get('roll_seconds',1.5)))
        self.visual.texture_path = self.properties['open_texture']
        return True

    def cancel(self, refund=True):
        if refund and self.paid:
            self.game.player.add_coins(self.paid)
        self.paid = 0;self.reward = None;self.state = 'Ready'
        self.visual.texture_path = self.properties['closed_texture']

    def update(self, dt):
        if self.state == 'Rolling':
            self.remaining -= dt
            if self.remaining <= 0:
                try:
                    if self.reward not in [k for k,w in self.catalog()]:raise ValueError('Reward resources changed during roll')
                    self.world.equip(self.reward)
                except Exception as exc:
                    self.cancel();self.game.warning = str(exc)
                    self.game.content.notify('BOX ERROR: COINS REFUNDED');return
                self.game.content.notify('NEW WEAPON: '+self.reward.upper())
                self.paid = 0;self.state = 'Reward';self.remaining = 1.2
        elif self.state == 'Reward':
            self.remaining -= dt
            if self.remaining <= 0:self.cancel(refund=False)

class ZombieWorld:
    def __init__(self, game):
        self.game = game;self.waves = game.waves
        self.config = game.director.properties.get('zombies',{})
        self.active_weapon = None
        self.gates = [Barricade(game,n) for n in game.scene.walk() if n.script_properties.get('zombie_role')=='barricade']
        boxes = [n for n in game.scene.walk() if n.script_properties.get('zombie_role')=='box']
        if not self.gates or not boxes:raise ValueError('Zombie scene requires a right barricade and a box')
        self.box = MysteryBox(self,boxes[0])
        self.navigator = Navigator(game,self.config)
        self.equip(self.config.get('starting_weapon','Pistol'))
        game.player.coins = max(0,int(self.config.get('starting_coins',60)))

    def equip(self, kind):
        p = self.game.player
        if kind not in p.weapons:raise ValueError('Unknown weapon: '+str(kind))
        # Unlock first. If this fails, the previous weapon and payment survive.
        p.weapons[kind].unlock()
        for key,w in p.weapons.items():
            if key != kind:
                w.unlocked = False;w.owner.visible = False;w.target = None;w.phase = 'Idle'
                for blade in w.blades:blade.visible = False
        self.active_weapon = kind
        p.riposte = False;p.parry_until = 0
        self.game.content.cosmetics(force=True)

    def configure(self, enemy, wave):
        c = self.config
        enemy.max_health = max(1,float(c.get('base_health',35))*(1+min(100,wave-1)*float(c.get('health_growth',.12))))
        enemy.health = enemy.max_health
        enemy.speed = min(float(c.get('max_speed',3.4)),float(c.get('base_speed',1.7))+(wave-1)*float(c.get('speed_growth',.025)))*PPU
        enemy.damage = min(100,float(c.get('base_damage',10))+(wave-1)*float(c.get('damage_growth',.5)))
        enemy.reward = max(1,int(c.get('kill_reward',10)))
        enemy.tint = (255,255,255,255);enemy.indicator_tint = enemy.tint
        enemy.armor = 0;enemy.resistance = 0
        enemy.visual.texture_path = c.get('zombie_texture','assets/zombies/zombie.png')
        scale = max(.01,float(c.get('zombie_scale',.15)))
        enemy.visual.scale = Vector2(scale,scale)
        enemy.visual.position = Vector2(*c.get('zombie_visual_offset',[.75,-.75]))
        enemy.visual.tint = enemy.tint
        enemy.owner.collision_mask |= BARRICADE
        enemy.gate = self.gates[0];enemy.entered_arena = False
        enemy.route = [];enemy.repath = self.game.time

    def move(self, enemy, dt):
        pos = enemy.owner.global_position;gate = enemy.gate
        gp = gate.node.global_position
        if not enemy.entered_arena:
            if pos.x <= gp.x-90 and abs(pos.y-gp.y) < 30:
                enemy.entered_arena = True
            else:
                # Three lanes limit crowding at the same right-hand opening.
                lane = getattr(enemy,'lane',0)
                target = Vector2(gp.x+42,gp.y+lane*32)
                if gate.broken:target = Vector2(gp.x-100,gp.y+lane*8)
                distance = (target-pos).length
                if not gate.broken and distance < 8:
                    enemy.owner.velocity = Vector2()
                    if self.game.time >= enemy.next_attack:
                        gate.hit(float(self.config.get('barricade_damage',12)))
                        enemy.next_attack = self.game.time+max(.2,float(self.config.get('barricade_attack_seconds',1)))
                    return
                enemy.owner.velocity = (target-pos).normalized*min(enemy.speed,distance/max(dt,.001))
                return
        target = self.game.player.owner.global_position
        nav = self.navigator
        if nav.clear(pos,target):
            enemy.route = [];direction = target-pos
        else:
            if self.game.time >= enemy.repath:
                enemy.route = nav.route(pos,target);enemy.repath = self.game.time+.8
            while enemy.route and (enemy.route[0]-pos).length < 10:enemy.route.pop(0)
            direction = enemy.route[0]-pos if enemy.route else Vector2()
        enemy.owner.velocity = direction.normalized*min(enemy.speed,direction.length/max(dt,.001))

    def prepare_wave(self):
        if self.config.get('restore_between_waves',False):
            for gate in self.gates:gate.restore()
            self.game.engine.physics.rebuild_queries_2d(self.game.engine.tree.root)

    def update(self, dt):
        self.box.update(dt)

    def hud(self):
        g = self.game;w = self.waves
        if g.gameover:
            g.set_text('zombie_status','ZOMBIES / RUN ENDED');g.show('box_interact',False);return
        status = 'WAVE '+str(w.current) if w.state=='Active' else 'NEXT WAVE IN '+str(max(0,math.ceil(w.delay)))
        g.set_text('run_modifier','ZOMBIES / '+status)
        g.set_text('zombie_status',status+' | PENDING: '+str(w.pending)+' | '+('B: UPGRADES' if w.intermission else 'SHOP LOCKED'))
        g.set_text('barricade_status','RIGHT BARRICADE: '+('BROKEN' if self.gates[0].broken else str(math.ceil(self.gates[0].health))+' HP'))
        for node in g.ui_buttons:
            if node.script_properties.get('action') in ['OpenShop','ToggleShop']:
                node.disabled = not w.intermission or g.paused
        box = self.box
        near = box.near()
        g.show('box_interact',near and not g.paused)
        button = g.roles.get('box_interact')
        if button:
            button.text = 'ROLLING...' if box.state=='Rolling' else 'E / X: BOX '+str(box.price)+'*'
            button.disabled = box.state!='Ready'
