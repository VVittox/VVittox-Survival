"""Integration checks: real scenes, scripts, physics and combat; no window required.
Run from bundle root: python -m unittest discover -s game/tests -v
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

GAME = Path(__file__).resolve().parents[1]
ENGINE = GAME.parent/'engine'
sys.path[:0] = [str(ENGINE),str(GAME)]
from engine.core.project_config import ProjectConfig
from engine.runtime_game import settings_from_project, _load_runtime_scene
from engine.core.engine import Engine
from engine.utils.vmath import Vector2
from engine.scene.ui_nodes import UIButton
from vvittox.zombies import BARRICADE

class Integration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=GAME.parent)
        self.previous = os.environ.get('VVITTOX_SAVE_DIR')
        os.environ['VVITTOX_SAVE_DIR'] = self.tmp.name
        self.cfg = ProjectConfig.load(GAME)
        self.engine = Engine(settings_from_project(self.cfg))
        self.engine.scene_loader = lambda name: _load_runtime_scene(self.cfg,name)

    def tearDown(self):
        self.engine.shutdown()
        if self.previous is None:os.environ.pop('VVITTOX_SAVE_DIR',None)
        else:os.environ['VVITTOX_SAVE_DIR'] = self.previous
        self.tmp.cleanup()

    def load(self, name):
        self.engine.set_scene(_load_runtime_scene(self.cfg,'scenes/'+name+'.vscene'))
        session = self.engine.current_scene._script_instance.session
        session.rng.seed(17)
        return session

    def step(self, seconds):
        for _ in range(round(seconds*60)):self.engine.advance_frame(1/60,render=False)

    def test_menu_restart_and_mode_isolation(self):
        s = self.load('Menu');s.action('StartGame')
        self.assertTrue(s.visible('mode_select'));self.assertFalse(s.visible('main'))
        s.action('ShowMain');self.assertTrue(s.visible('main'))
        s.action('StartGame');s.action('StartZombie');self.engine._apply_scene_change()
        z = self.engine.current_scene._script_instance.session
        self.assertTrue(z.is_zombie);z.record_wave(7);z.record_kill()
        z.player.coins = 1000;z.action('RestartGame');self.engine._apply_scene_change()
        fresh = self.engine.current_scene._script_instance.session
        self.assertTrue(fresh.is_zombie);self.assertEqual(fresh.player.coins,60)
        self.assertEqual(fresh.waves.current,0);self.assertEqual(len(fresh.enemies),0)
        fresh.action('ReturnToMenu');self.engine._apply_scene_change()
        menu = self.engine.current_scene._script_instance.session
        menu.action('StartGame');menu.action('StartClassic');self.engine._apply_scene_change()
        c = self.engine.current_scene._script_instance.session
        self.assertFalse(c.is_zombie);self.assertEqual(c.profile.get('Save.BestWave'),0)
        self.assertEqual(c.profile.get('Save.ZombieBestWave'),7)
        self.assertEqual(c.profile.get('Save.LifetimeKills'),0)
        self.assertTrue(c.player.weapons['Knife'].unlocked)
        c.toggle_shop();c.player.coins = 1000
        self.assertTrue(c.shop.buy('BuyAutomatic'))
        directors = [n for n in self.engine.tree.root.walk() if n.script_path=='scripts/director.py']
        self.assertEqual(len(directors),1)

    def test_box_payment_roll_pause_refund_and_one_slot(self):
        s = self.load('Zombie');b = s.zombies.box
        s.player.owner.position = Vector2(b.node.position.x,b.node.position.y)
        s.player.coins = 59;self.assertFalse(b.buy());self.assertEqual(s.player.coins,59)
        s.player.coins = 120;self.assertTrue(b.buy())
        reward = b.reward
        for _ in range(20):self.assertFalse(b.buy())
        self.assertEqual(s.player.coins,60)
        s.toggle_pause();remaining = b.remaining;self.step(2)
        self.assertEqual(b.remaining,remaining);self.assertEqual(s.zombies.active_weapon,'Pistol')
        s.toggle_pause();self.step(1.6)
        self.assertEqual(s.zombies.active_weapon,reward)
        self.assertEqual([k for k,w in s.player.weapons.items() if w.unlocked],[reward])
        self.assertEqual(s.player.coins,60)
        self.step(1.3);self.assertEqual(b.state,'Ready')
        # Invalid resources are excluded before payment.
        old_table = b.properties['weapons'];b.properties['weapons']=[{'id':'Missing','weight':1}]
        self.assertFalse(b.buy());self.assertEqual(s.player.coins,60)
        b.properties['weapons']=old_table;self.assertTrue(b.buy())
        old_equip = s.zombies.equip
        def fail(kind):raise ValueError('simulated award failure')
        s.zombies.equip = fail;self.step(1.6)
        self.assertEqual(s.player.coins,60);self.assertEqual(b.state,'Ready')
        s.zombies.equip = old_equip

    def test_shop_and_upgrade_boundary_guards(self):
        s = self.load('Zombie');s.player.coins = 1000
        self.assertFalse(s.shop.buy('BuyAutomatic'))
        s.toggle_shop();self.assertTrue(s.visible('shop_extra'));self.assertFalse(s.visible('shop'))
        self.assertFalse(s.shop.buy('BuyAutomatic'))
        hp = s.player.max_health;self.assertTrue(s.shop.buy('BuyHealth'));self.assertGreater(s.player.max_health,hp)
        s.action('ShopBack');self.assertFalse(s.paused);s.waves.start_wave()
        before = s.player.coins
        for action in ['BuyHealth','BuyKnife','BuyAutomatic']:self.assertFalse(s.shop.buy(action))
        s.toggle_shop();self.assertFalse(s.visible('shop_extra'))
        s.action('ShopExtra');self.assertFalse(s.visible('shop_extra'))
        s.show_upgrades();self.assertFalse(s.visible('upgrade'))
        self.assertEqual(s.player.coins,before)

    def test_pending_spawns_blocking_three_waves_and_single_reward(self):
        s = self.load('Zombie');w = s.waves;w.start_wave()
        positions = w.properties['spawn_positions'];w.properties['spawn_positions']=[[340, -170]]
        self.step(1);self.assertEqual(w.pending,w.spawn_total);self.assertEqual(w.current,1)
        self.assertEqual(w.state,'Active');self.assertEqual(w.alive,0)
        w.properties['spawn_positions'] = positions
        for expected in range(1,4):
            # Kill through the real damage/removal path while new enemies are pending.
            for _ in range(900):
                self.step(1/60)
                for enemy in tuple(s.enemies):
                    coins = s.player.coins;reward = enemy.reward
                    enemy.take_damage(1e9);enemy.take_damage(1e9)
                    self.assertGreaterEqual(s.player.coins,coins+reward)
                if w.state=='Intermission':break
            self.assertEqual(w.current,expected);self.assertEqual(w.pending,0);self.assertEqual(w.alive,0)
            self.assertTrue(s.visible('upgrade'));self.assertTrue(s.paused)
            self.step(.2);self.assertTrue(s.choose_upgrade(0))
            self.assertFalse(s.paused)
            self.assertTrue(w.start_wave())
        self.assertEqual(w.current,4)

    def test_barricade_real_attacks_collision_and_navigation(self):
        s = self.load('Zombie');g = s.zombies.gates[0]
        self.assertGreater(g.node.position.x,s.player.owner.position.x)
        self.assertEqual(len(s.zombies.gates),1)
        self.step(11)
        self.assertTrue(g.broken);self.assertEqual(g.destroy_count,1)
        self.assertFalse(g.node.collider.enabled)
        self.assertEqual(g.visual.texture_path,g.properties['broken_texture'])
        before = g.visual.position;self.assertFalse(g.hit(999));self.assertEqual(g.destroy_count,1)
        self.step(8)
        self.assertTrue(any(e.entered_arena for e in s.enemies) or s.kills>0)
        # Route from the previously troublesome lower lane to the actual player.
        route = s.zombies.navigator.route(Vector2(240,103),s.player.owner.global_position)
        self.assertTrue(route)
        self.assertEqual(g.visual.position,before)
        self.assertFalse(self.engine.physics.raycast_2d(self.engine.tree.root,Vector2(390,95),Vector2(290,95),collision_mask=BARRICADE))
        g.restore();self.engine.physics.rebuild_queries_2d(self.engine.tree.root)
        self.assertTrue(self.engine.physics.raycast_2d(self.engine.tree.root,Vector2(390,95),Vector2(290,95),collision_mask=BARRICADE))

    def test_natural_first_wave_combat_no_stranded_zombies(self):
        s = self.load('Zombie')
        for _ in range(45):
            self.step(1)
            if s.waves.state=='Intermission' or s.gameover:break
        self.assertFalse(s.gameover)
        self.assertEqual(s.waves.state,'Intermission')
        self.assertEqual(s.kills,6)
        self.assertEqual(len(s.enemies),0)

    def test_death_cancels_roll_and_stops_waves(self):
        s = self.load('Zombie');b = s.zombies.box
        s.player.owner.position = Vector2(b.node.position.x,b.node.position.y)
        self.assertTrue(b.buy());before = s.zombies.active_weapon
        s.player.take_damage(1e9);self.step(5)
        self.assertTrue(s.gameover);self.assertEqual(s.waves.state,'Stopped')
        self.assertEqual(s.zombies.active_weapon,before);self.assertEqual(b.state,'Ready')
        self.assertEqual(s.waves.pending,0)

    def test_ui_scaled_hit_rects_and_assets(self):
        s = self.load('Menu');s.action('StartGame')
        for width,height in [(800,450),(1280,720),(1920,1080),(1024,768),(2560,1080)]:
            for n in s.roles['mode_select'].walk():
                if isinstance(n,UIButton):
                    pos,size = n.resolved_rect(Vector2(width,height))
                    self.assertGreaterEqual(pos.x,0);self.assertGreaterEqual(pos.y,0)
                    self.assertLessEqual(pos.x+size.x,width+.01);self.assertLessEqual(pos.y+size.y,height+.01)
                    self.assertGreater(size.y,30)
        s = self.load('Zombie')
        for n in s.scene.walk():
            for attr in ['texture_path','font_path','clip_path','stream_path']:
                value = getattr(n,attr,'')
                if value:self.assertTrue((GAME/value).exists(),value)
        for width,height in [(800,450),(1920,1080),(1024,768)]:
            for key in ['box_interact','zombie_status','barricade_status']:
                pos,size = s.roles[key].resolved_rect(Vector2(width,height))
                self.assertGreaterEqual(pos.x,0);self.assertGreaterEqual(pos.y,0)
                self.assertLessEqual(pos.x+size.x,width+.01);self.assertLessEqual(pos.y+size.y,height+.01)

if __name__=='__main__':unittest.main()
