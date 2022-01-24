from __future__ import annotations

from .tree import Tree
from ..data import Genotypes, Phenotypes
from .variant import Variant
from .haplotypes import Haplotype
from .assoc_test import AssocTest, AssocTestSimple


class TreeBuilder:
    """
    Creates a Tree object from provided Genotypes and Phenotypes

    Attributes
    ----------
    tree: Tree
        A tree representing haplotypes composed from trait-associated genotypes
    gens: Genotypes
        The genotypes from which the tree should be built
    phens: Phenotypes
        The phenotypes from which the tree should be built
    method: AssocTest, optional
        The type of association test to perform at each node when constructing the tree
    """

    def __init__(
        self,
        genotypes: Genotypes,
        phenotypes: Phenotypes,
        method: AssocTest = AssocTestSimple(),
    ):
        self.gens = genotypes
        self.phens = phenotypes
        self.method = method
        self.tree = None

    def __repr__(self):
        return str((self.gens, self.phens))

    def run(self, root: int):
        """
        Run the tree builder and create a tree rooted at the provided variant

        Parameters
        ----------
        root : int
            The index of the variant to use at the root of tree. This should be an
            index into :py:attr:`~.TreeBuilder.gens.variants`
        """
        if self.tree is not None:
            raise AssertionError(
                "A tree already exists for this TreeBuilder. Please create a new one."
            )
        # step one: initialize the tree
        root_node = Variant.from_np(self.gens.variants[root], idx=root)
        self.tree = Tree(root_node)
        # step two: create the tree
        self._create_tree(root_node)
        return self.tree

    def _create_tree(
        self, parent: Variant, parent_hap: Haplotype = None, parent_idx: int = 0
    ):
        """
        Recursive helper to the run() function

        Adds a subtree under the node with index parent_idx in the tree

        Parameters
        ----------
        parent : Variant
            An existing node in the tree under which we should consider creating a subtree
        parent_hap : Haplotype
            The haplotype containing all variants up to (but NOT including) the parent
        parent_idx : int
            The index of the parent node in the tree
        """
        # we consider two possible alleles
        alleles = (0, 1)
        for allele in alleles:
            variant_gts = self.gens.data[:, parent.idx, allele]
            # create a new Haplotype if we don't have on yet
            # else, create a new one with parent added
            if parent_hap is None:
                new_parent_hap = Haplotype.from_node(parent, allele, variant_gts)
            else:
                new_parent_hap = parent_hap.append(parent, allele, variant_gts)
            # find the best variant, add it to the tree, and then create a new subtree
            # under it
            best_variant, results = self._find_split(new_parent_hap, parent_idx, allele)
            if best_variant is None:
                continue
            new_node_idx = self.tree.add_node(best_variant, parent_idx, allele, results)
            self._create_tree(best_variant, new_parent_hap, new_node_idx)

    def _find_split(
        self, parent: Haplotype, parent_idx: int, allele: int
    ) -> tuple[Variant, np.void]:
        """
        Find the variant that best fits under the parent_idx node with the allele edge

        Parameters
        ----------
        parent : Haplotype
            The haplotype containing all variants up to (and including) the parent
        parent_idx : int
            The index of the parent node in the tree
        allele : int
            The allele of the parent node in the tree

        Returns
        -------
        tuple[Variant, float]
            The variant that best fits under the parent node with the allele edge AND
            the results (ex: beta, pval) of the haplotype association test after
            incorporating that variant
        """
        # step 1: transform the GT matrix into a haplotype matrix
        hap_matrix = parent.transform(self.gens)
        if hap_matrix.shape[1] == 0:
            # if there weren't any genotypes left, just return None
            return None, None
        # step 2: run all association tests on all of the haplotypes
        results = self.method.run(hap_matrix.sum(axis=2), self.phens.data)
        p_values = results.data["pval"]
        # step 3: find the index of the best variant within the haplotype matrix
        best_p_idx = p_values.argmin()
        best = results.data[best_p_idx]
        # step 4: check whether we should terminate the branch
        if self.check_terminate_branch(best["pval"], len(p_values)):
            return None, best
        # step 5: find the index of the best variant within the genotype matrix
        # we need to account for indices that we removed when running transform()
        # There might be a faster way of doing this but for now we're just going to
        # live with it
        for gt_idx in sorted(parent.node_indices):
            # add each idx back in, so long as they are less than the target idx
            if gt_idx > best_p_idx:
                break
            best_p_idx += 1
        # step 6: return the Variant with the best p-value
        return Variant.from_np(self.gens.variants[best_p_idx], best_p_idx), best

    def check_terminate_branch(self, pval: float, num_tests: int) -> bool:
        """
        Check whether this branch should be terminated.

        Parameters
        ----------
        pval : float
            The best p-value amongst all tests performed on this branch.
        num_tests : int
            The number of tests performed on this branch.

        Returns
        -------
        bool
            True if the branch should be terminated, False otherwise
        """
        # correct for multiple hypothesis testing
        # For now, we use the Bonferroni correction
        # TODO: perform a likelihood ratio test?
        return pval >= self.method.pval_thresh / num_tests