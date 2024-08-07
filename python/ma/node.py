from collections import OrderedDict
from typing import Optional

from . import KeepSel, cmds, log, name_to_node, om

logger = log.get_logger(__name__)
SYSTEM_TYPE_ATTR_NAME = 'system_type'


def add_system_attr(obj: str, value: str):
    """Add the SystemType attribute to a node.

    Used to identify and cast instances of System subclasses.

    Args:
        obj: name of maya node where to add the attribute.
        value: system type value.
    """
    if not cmds.attributeQuery(SYSTEM_TYPE_ATTR_NAME, n=obj, ex=1):
        cmds.addAttr(obj, ln=SYSTEM_TYPE_ATTR_NAME, dt='string')
    cmds.setAttr('.'.join([obj, SYSTEM_TYPE_ATTR_NAME]), value, type='string')


class Node(str):
    """Baseclass for complex structures represented by a Maya node.

    The class derives from str and is initialized with a node's UUID.
    """

    DEFAULT_NAME: str = 'grp'
    """Default node name when using namespaces."""
    _NODETYPE: str = 'transform'
    """Type of node to be created as root object"""
    dependnode: om.MObject = None
    """Cached api object of this system's root node."""
    fn: om.MFnDependencyNode
    """Cached api function set to work with this system's root DependNode."""

    def __new__(cls, value: str | om.MObject) -> 'Node':
        """Initialize a Node from its root node uuid.

        Args:
            value: uuid or name of a maya node. If a name
                is passed, replace by object's uuid.

        Returns:
            instance, or None if object doesn't exist.
        """
        if isinstance(value, str):
            value = name_to_node(value)
        if value:
            fn = om.MFnDagNode()
            if fn.hasObj(value):
                fn.setObject(value)
            else:
                fn = om.MFnDependencyNode(value)
            self = super().__new__(cls, fn.uuid())
            self.dependnode = value
            self._fn = fn
            return self

    def __eq__(self, other: 'Node') -> bool:
        """Nodes are equal if their class and str conversion (uuid) are equal.

        Args:
            other: value to check for equality (usually a Node subclass).

        Returns:
            True if input value is equal to this Node instance.
        """
        return self.__class__ == other.__class__ and super().__eq__(other)

    def __hash__(self) -> int:
        return hash(str(self))

    def __repr__(self) -> str:
        """String representation of a Node.

        Returns:
            "<node type>('root name')". Example: Asset('duck')
        """
        return f"{type(self).__name__}('{self.name}')"

    @classmethod
    def create(
            cls, name: Optional[str] = None, parent: Optional[str] = None
    ) -> 'Node':
        """Create a new Node in current maya scene.

        The node is created based on the `nodetype` variable defined for
        each Node (sub)class, and a 'system type' attribute is added to it
        with the class name as its value.

        Args:
            name: name of the new node. If not provided,
                use the node type, as Maya would do, letting the software
                resolve name clashes with an index at the end.
            parent: name or uuid of parent object. If none
                provided, use the scene's root.

        Returns:
            class instance.
        """
        if parent is not None:
            parent = cmds.ls(parent)[0]
        name = name or cls._NODETYPE
        logger.debug(f"Creating {cls.__name__}({name})")
        if name.endswith(':'):
            name += cls.DEFAULT_NAME
        root = cmds.createNode(cls._NODETYPE, name=name, parent=parent, ss=1)
        return cls(root)

    @classmethod
    def deserialize(
            cls,
            name: Optional[str] = None,
            parent: Optional[str] = None,
            *args,
            **kwargs
    ) -> 'Node':
        """Create a Node out of serialized data.

        Args:
            name: name of the new Node. If not provided,
                use the node type, as Maya would do, letting the software
                resolve name clashes with an index at the end.
            parent: name or uuid of parent object.
            args: passed on to default constructor (create method).
            kwargs: passed on to default constructor (create method).

        Returns:
            class instance.
        """
        return cls.create(name=name, parent=parent, *args, **kwargs)

    def delete(self):
        """Delete this Node"""
        ns = self.namespace
        node_repr = repr(self)
        cmds.delete(self.name)
        if ns and not cmds.namespaceInfo(ns, ls=1):
            cmds.namespace(rm=ns)
        logger.debug(f"{node_repr} deleted")

    @KeepSel()
    def export(self, filename: str, **kwargs):
        """Export this Node to a maya ascii file.

        Args:
            filename: full path to the saved file.
        """
        cmds.select(self.name)
        settings = {'pr': 1, 'typ': 'mayaAscii'}
        settings.update(**kwargs)
        cmds.file(filename, es=True, **settings)
        logger.info(f'{self!r} exported to {filename}')

    def get_name(self) -> str:
        """Get the name of the maya node.

        Returns:
            name of this node
        """
        if isinstance(self.fn, om.MFnDagNode):
            return self.fn.partialPathName()
        return self.fn.name()

    def rename(self, value: str):
        """Set the name of the maya node.

        Args:
            value: new name
        """
        sep = ':'
        if sep in self.name:
            if sep in value:
                self.namespace = value.rsplit(sep, 1)[0]
            else:
                self.namespace = ''
        if value[-1] == sep:
            value += self.DEFAULT_NAME
        cmds.rename(self.name, value)

    def serialize(self) -> OrderedDict:
        """Serialize this Node instance.

        Returns:
            required data to rebuild this Node (sub)class.
        """
        logger.log(5, f'Serializing {self!r}')
        return OrderedDict(type=self.__class__.__name__)

    name = property(get_name, rename)

    @property
    def fn(self) -> om.MFnDependencyNode:
        if om.MObjectHandle(self.dependnode).isValid():
            return self._fn
        raise RuntimeError(
            f'Invalid depend node. {type(self).__name__}({self}) not found')

    @property
    def namespace(self) -> str:
        """The namespace part (if any) of this maya node's name.

        Args:
            value: new namespace for the maya node.

        Returns:
            namespace of the maya node.
        """
        return self.fn.namespace

    @namespace.setter
    def namespace(self, value: str):
        ns = self.namespace
        if ns:
            if value:
                sep = ':'
                if cmds.namespace(ex=value):
                    cmds.namespace(mv=(ns, value))
                elif sep in value:
                    par, value = value.rsplit(sep, 1)
                    if not cmds.namespace(ex=par):
                        cmds.namespace(add=par)
                    cmds.namespace(ren=(self.namespace, value), p=par)
                else:
                    cmds.namespace(ren=(self.namespace, value))
            else:
                cmds.namespace(rm=ns, mnr=1)

    @property
    def nodename(self) -> str:
        """Maya node name (path excluded).

        Returns:
            node name.
        """
        return self.fn.name()


class System(Node):
    """Systems in maya are structures identified by a root node.

    The root has a 'system type' attribute, informing on the system subclass
    used to instantiate the system. This allows easy and systematic recognition
    of scene contents that may require so.
    """

    @classmethod
    def create(
            cls, name: Optional[str] = None, parent: Optional[str] = None
    ) -> 'System':
        """Create a new System in current maya scene.

        The root node is created, based on the `nodetype` variable defined for
        each System (sub)class, and a 'system type' attribute is added to it
        with the class name as its value.

        Args:
            name: name of the new system. If not provided, use the node type, as
                Maya would do, letting the software resolve name clashes with an
                index at the end.
            parent: name or uuid of parent object. If none provided, use the
                scene's root.

        Returns:
            class instance.
        """
        self: System = super().create(name, parent)
        self.create_attributes()
        return self

    def create_attributes(self):
        """Add any missing attributes expected in this system."""
        add_system_attr(self.name, self.__class__.__name__)

    @property
    def type(self) -> str:
        """Get/set the system type attribute's value.

        Args:
            value: new value for the attribute. Modifying this value will change
                the class that gets initiated the next type a system is
                instantiated with this node through the Systems Factory.

        Returns:
            current value of the system type attribute
        """
        return cmds.getAttr(f'{self.name}.{SYSTEM_TYPE_ATTR_NAME}')

    @type.setter
    def type(self, value: str):
        cmds.setAttr(
            '.'.join([self.name, SYSTEM_TYPE_ATTR_NAME]),
            value, type='string')


class Factory(dict):
    """Systems factories keep a registry of available systems types.

    Used for dynamically constructing System instances out of maya objects.
    """

    fn: om.MFnDependencyNode
    """Reusable function set for identifying and instantiating Systems based on
    maya scene nodes."""

    def __init__(self, cls: Optional[System] = None):
        """Initialize a Factory.

        Args:
            cls: If provided, register input class and all it's (loaded)
                subclasses.
        """
        super().__init__()
        self.fn = om.MFnDependencyNode()
        if cls:
            self.register(cls)

    def get_system(self, obj: str | om.MObject) -> Optional[System]:
        """Initialize adequate System type, provided its root object.

        Args:
            obj: name or uuid of system's root node, or
                corresponding MObject.

        Returns:
            (sub)class instance.
        """
        cls = self.get_system_class(obj)
        if cls is not None:
            return cls(obj)

    def get_system_class(self, obj: str | om.MObject) -> Optional[type]:
        """Get the adequate System type for input node.

        Node must have a 'system type' attribute to qualify as a System's root.

        Args:
            obj: name or uuid of system's root node, or corresponding MObject.

        Returns:
            System (sub)class.
        """
        if isinstance(obj, str):
            obj = name_to_node(obj)
        if obj:
            fn = self.fn
            fn.setObject(obj)
            if fn.hasAttribute(SYSTEM_TYPE_ATTR_NAME):
                return self.get(
                    fn.findPlug(SYSTEM_TYPE_ATTR_NAME, True).asString(),
                    System)

    def register(self, cls: type):
        """Add input class and all it's subclasses to the systems factory.

        Recursively import all submodules in a package and add contained
        subclasses to the systems_factory.

        Args:
            cls: class to be registered.
        """
        self[cls.__name__] = cls
        [self.register(x) for x in cls.__subclasses__()]


factory = Factory(System)
