export interface KitDueTreeNode {
	item_code: string;
	item_name: string;
	qty_per: number;
	total_qty: number;
	is_kit_item: number;
	is_kit_set: number;
	next_due_date: string | null;
	quantity_due_in: number;
	available_qty?: number;
	cycle: number;
	children: KitDueTreeNode[];
}

export interface KitDueTreeRow {
	key: string;
	depth: number;
	node: KitDueTreeNode;
	hasChildren: boolean;
}

/**
 * Flatten the kit tree into display rows, skipping the descendants of any
 * row whose key is in `collapsed`. Keys are the item-code path, so the same
 * component under two different parents toggles independently.
 */
export function flattenKitDueTree(
	root: KitDueTreeNode | null | undefined,
	collapsed: Set<string>,
): KitDueTreeRow[] {
	const rows: KitDueTreeRow[] = [];
	if (!root) return rows;

	const walk = (node: KitDueTreeNode, depth: number, parentKey: string, index: number) => {
		const key = parentKey ? `${parentKey}/${index}:${node.item_code}` : node.item_code;
		const children = Array.isArray(node.children) ? node.children : [];
		rows.push({ key, depth, node, hasChildren: children.length > 0 });
		if (collapsed.has(key)) return;
		children.forEach((child, i) => walk(child, depth + 1, key, i));
	};

	walk(root, 0, "", 0);
	return rows;
}
