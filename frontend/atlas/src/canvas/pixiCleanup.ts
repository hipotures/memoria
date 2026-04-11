type DestroyableChild = {
  destroy: (options?: { children?: boolean }) => void;
};

type ContainerLike = {
  removeChildren: () => DestroyableChild[];
};

export function clearPixiContainer(container: ContainerLike) {
  const children = container.removeChildren();
  children.forEach((child) => {
    child.destroy({ children: true });
  });
}
