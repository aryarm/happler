#!/usr/bin/env python
from pathlib import Path
from logging import Logger

import click
import numpy as np

from haptools.logging import getLogger
from haptools.ld import pearson_corr_ld
from haptools.data import Data, Genotypes, GenotypesPLINK


@click.command()
@click.argument("gts", type=click.Path(exists=True, path_type=Path))
@click.argument("target", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--region",
    type=str,
    default=None,
    show_default="all genotypes",
    help="""
    The region from which to extract genotypes; ex: 'chr1:1234-34566' or 'chr7'\n
    For this to work, the VCF must be indexed and the seqname must match!""",
)
@click.option(
    "-i",
    "--hap-id",
    type=str,
    show_default="the first haplotype ID",
    help=(
        "A haplotype ID from the target file to use"
        "(ex: '-i H1')."
    ),
)
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    default=Path("/dev/stdout"),
    show_default="stdout",
    help="A .ld file containing the LD results for each SNP in gts",
)
@click.option(
    "-v",
    "--verbosity",
    type=click.Choice(["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"]),
    default="DEBUG",
    show_default=True,
    help="The level of verbosity desired",
)
def main(
    gts: Path,
    target: Path,
    region: str = None,
    hap_id: str = None,
    output: Path = Path("/dev/stdout"),
    verbosity: str = "DEBUG",
):
    """
    Compute LD between a SNP in a PGEN file and all other SNPs in a different
    PGEN file
    """
    log = getLogger("compute_pgen_ld", verbosity)

    log.info("Loading target genotypes")
    target = GenotypesPLINK(fname=target, log=log)
    target.read(variants=set((hap_id,)) if hap_id is not None else None)
    target.check_missing()
    target.check_biallelic()

    if hap_id is None:
        target.subset(variants=(target.variants["id"][0],), inplace=True)

    log.info("Loading reference genotypes")
    gts = GenotypesPLINK(fname=gts, log=log)
    gts.read(samples=set(target.samples), region=region)
    gts.check_missing()
    gts.check_biallelic()
    # important: check that samples are ordered the same in each file!
    assert gts.samples == target.samples

    log.info("Summing target genotypes")
    target_gts = target.data[:, 0, :2].sum(axis=1)

    log.info("Computing LD between genotypes and the target")
    with Data.hook_compressed(output, mode="w") as ld_file:
        log.info("Outputting .ld file with LD values")
        ld_file.write("CHR\tBP\tSNP\tR\n")
        for idx, variant in enumerate(gts.variants):
            var_chr, var_bp, var_snp = variant[["chrom", "pos", "id"]]
            variant_gts = gts.data[:, idx, :2].sum(axis=1)
            variant_ld = pearson_corr_ld(target_gts, variant_gts)
            ld_file.write(f"{var_chr}\t{var_bp}\t{var_snp}\t{variant_ld:.3f}\n")


if __name__ == "__main__":
    main()