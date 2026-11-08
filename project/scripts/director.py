from engine.scripting import VScript
from vvittox.session import Session

class Script(VScript):
    def __init__(self,owner):
        super().__init__(owner);self.session=Session(self)
    def _ready(self):self.session.ready()
    def _process(self,delta):self.session.process(delta)
    def _physics_process(self,delta):self.session.physics(delta)
    def _before_exit_tree(self):self.session.changing_scene=True
    def _exit_tree(self):self.session.exit()
