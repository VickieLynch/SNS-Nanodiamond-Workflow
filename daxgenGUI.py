#!/usr/bin/env python
import os
import sys
import string
import subprocess
from ConfigParser import ConfigParser
from Pegasus.DAX3 import *
from Tkinter import *
import tkSimpleDialog

class MyDialog(tkSimpleDialog.Dialog):

    def body(self, master):

        self.label_text = []
        self.label_name = []
        parameters = []
        try:
            # Read user input parameters
            user_input = open('test.cfg', 'r')
            self.header = user_input.readline()
            # while True:
            for i in range(38):
                lineString = user_input.readline()
                lineList = lineString.split()
                if len(lineList) < 2:  # check for blank record
                    continue
                if lineList[0] == "#":  # check for commentd
                    self.label_text.append( lineString )
                else:
                    lineList = lineString.split("=")
                    self.label_name.append(lineList[0])
                    parameters.append(lineList[1])
            user_input.close()
        except:
            for i in range(16):
                parameters.append('')

        Message(master,
            text = (
                "The DAX generator will create a separate pipeline of jobs for each value of epsilon "
                + "\n\nDefault user input values are obtained from test.cfg if it exists. A new test.cfg file will be written."),
            anchor=E, aspect=1000, bg='yellow').grid(row=0, columnspan=2)

        for i in range( len( self.label_text) ):
            j = i+1
            Label(master, text = self.label_text[i]).grid(row = j, column = 1, sticky = W)

        # Populate entry boxes with default values
        self.entry = []
        number_of_params = len( parameters )
        for i in range(number_of_params):
            self.entry.append( Entry( master, width = 30) )
            self.entry[i].insert( 0, parameters[i] )
            j = i+1
            self.entry[i].grid( row = j, column = 0, sticky = W )

    def apply(self):

        self.result = []
        for i in range ( len(self.entry) ):
            if len( self.entry[i].get() ) == 0:  # check for blank input
                self.result.append( '0' )
                continue
            self.result.append( self.entry[i].get() )


DAXGEN_DIR = os.path.dirname(os.path.realpath(__file__))
TEMPLATE_DIR = os.path.join(DAXGEN_DIR, "templates")

def format_template(name, outfile, **kwargs):
    "This fills in the values for the template called 'name' and writes it to 'outfile'"
    templatefile = os.path.join(TEMPLATE_DIR, name)
    template = open(templatefile).read()
    formatter = string.Formatter()
    data = formatter.format(template, **kwargs)
    f = open(outfile, "w")
    try:
        f.write(data)
    finally:
        f.close()

class RefinementWorkflow(object):
    def __init__(self, outdir, config):
        "'outdir' is the directory where the workflow is written, and 'config' is a ConfigParser object"
        self.outdir = outdir
        self.config = config
        self.daxfile = os.path.join(self.outdir, "dax.xml")
        self.replicas = {}

        # Get all the values from the config file
        self.epsilons = [x.strip() for x in config.get("simulation", "epsilons").split(",")]
        self.temperature = config.get("simulation", "temperature")
        self.equilibrate_steps = config.get("simulation", "equilibrate_steps")
        self.production_steps = config.get("simulation", "production_steps")
        self.sassena_pdb = config.get("simulation", "sassena_pdb")
        self.coordinates = config.get("simulation", "coordinates")
        self.structure = config.get("simulation", "structure")
        self.fixed_pdb = config.get("simulation", "fixed_pdb")
        self.extended_system = config.get("simulation", "extended_system")
        self.bin_coordinates = config.get("simulation", "bin_coordinates")
        self.bin_velocities = config.get("simulation", "bin_velocities")
        self.sassena_db = config.get("simulation", "sassena_db")
        self.incoherent_db = "database/db-neutron-incoherent.xml"
        self.coherent_db = "database/db-neutron-coherent.xml"

    def add_replica(self, name, path):
        "Add a replica entry to the replica catalog for the workflow"
        url = "file://%s" % path
        self.replicas[name] = url

    def generate_replica_catalog(self):
        "Write the replica catalog for this workflow to a file"
        path = os.path.join(self.outdir, "rc.txt")
        f = open(path, "w")
        try:
            for name, url in self.replicas.items():
                f.write('%-30s %-100s pool="local"\n' % (name, url))
        finally:
            f.close()

    def generate_prm(self, epsilon):
        "Generate an prm files for epsilon'"
        name = "par%s.prm" % epsilon
        path = os.path.join(self.outdir, name)
        kw = {
            "epsilon": "%10.6f" % (-0.01 * float(epsilon)),
        }
        format_template("8ND_8RNA_epsilon.xml", path, **kw)
        self.add_replica(name, path)

    def generate_eq_conf(self, epsilon, parameters):
        "Generate an equilibrate configuration file for 'epsilon'"
        name = "equilibrate_%s.conf" % epsilon
        path = os.path.join(self.outdir, name)
        kw = {
            "temperature": self.temperature,
            "epsilon": epsilon,
            "structure": self.structure,
            "coordinates": self.coordinates,
            "parameters": parameters,
            "fixed_pdb": self.fixed_pdb,
            "outputname": "equilibrate_%s" % epsilon,
            "extended_system": self.extended_system,
            "bin_coordinates": self.bin_coordinates,
            "bin_velocities": self.bin_velocities,
            "timesteps": self.equilibrate_steps
        }
        format_template("equilibrate.conf", path, **kw)
        self.add_replica(name, path)

    def generate_prod_conf(self, epsilon, parameters):
        "Generate a production configuration file for 'epsilon'"
        name = "production_%s.conf" % epsilon
        path = os.path.join(self.outdir, name)
        kw = {
            "temperature": self.temperature,
            "epsilon": epsilon,
            "structure": self.structure,
            "coordinates": self.coordinates,
            "parameters": parameters,
            "fixed_pdb": self.fixed_pdb,
            "inputname": "equilibrate_%s" % epsilon,
            "outputname": "production_%s" % epsilon,
            "timesteps": self.production_steps
        }
        format_template("production.conf", path, **kw)
        self.add_replica(name, path)

    def generate_ptraj_conf(self, epsilon):
        "Generate a ptraj configuration file for 'epsilon'"
        name = "ptraj_%s.conf" % epsilon
        path = os.path.join(self.outdir, name)
        kw = {
            "trajectory_input": "production_%s.dcd" % epsilon,
            "trajectory_output": "ptraj_%s.dcd" % epsilon
        }
        format_template("rms2first.ptraj", path, **kw)
        self.add_replica(name, path)

    def generate_incoherent_conf(self, epsilon):
        "Generate a sassena incoherent config file for 'epsilon'"
        name = "sassenaInc_%s.xml" % epsilon
        path = os.path.join(self.outdir, name)
        kw = {
            "sassena_pdb": self.sassena_pdb,
            "trajectory": "ptraj_%s.dcd" % epsilon,
            "output": "fqt_inc_%s.hd5" % epsilon,
            "database": self.incoherent_db
        }
        format_template("sassenaInc.xml", path, **kw)
        self.add_replica(name, path)

    def generate_coherent_conf(self, epsilon):
        "Generate a sassena coherent config file for 'epsilon'"
        name = "sassenaCoh_%s.xml" % epsilon
        path = os.path.join(self.outdir, name)
        kw = {
            "sassena_pdb": self.sassena_pdb,
            "trajectory": "ptraj_%s.dcd" % epsilon,
            "output": "fqt_coh_%s.hd5" % epsilon,
            "database": self.coherent_db
        }
        format_template("sassenaCoh.xml", path, **kw)
        self.add_replica(name, path)

    def generate_workflow(self):
        "Generate a workflow (DAX, config files, and replica catalog)"
        dax = ADAG("refinement")

        # These are all the global input files for the workflow
        sassena_pdb = File(self.sassena_pdb)
        coordinates = File(self.coordinates)
        sassena_pdb = File(self.sassena_pdb)
        structure = File(self.structure)
        fixed_pdb = File(self.fixed_pdb)
        extended_system = File(self.extended_system)
        bin_coordinates = File(self.bin_coordinates)
        bin_velocities = File(self.bin_velocities)
        sassena_db = File(self.sassena_db)
        incoherent_db = File(self.incoherent_db)
        coherent_db = File(self.coherent_db)

        # This job untars the sassena db and makes it available to the other
        # jobs in the workflow
        untarjob = Job("tar", node_label="untar")
        untarjob.addArguments("-xzvf", sassena_db)
        untarjob.uses(sassena_db, link=Link.INPUT)
        untarjob.uses(incoherent_db, link=Link.OUTPUT, transfer=False)
        untarjob.uses(coherent_db, link=Link.OUTPUT, transfer=False)
        untarjob.profile("globus", "jobtype", "single")
        untarjob.profile("globus", "maxwalltime", "1")
        untarjob.profile("globus", "count", "1")
        dax.addJob(untarjob)

        # For each epsilon that was listed in the config file
        for epsilon in self.epsilons:

            parameters = "par%s.prm" % epsilon

            # Equilibrate files
            eq_conf = File("equilibrate_%s.conf" % epsilon)
            eq_coord = File("equilibrate_%s.restart.coord" % epsilon)
            eq_xsc = File("equilibrate_%s.restart.xsc" % epsilon)
            eq_vel = File("equilibrate_%s.restart.vel" % epsilon)

            # Production files
            prod_conf = File("production_%s.conf" % epsilon)
            prod_dcd = File("production_%s.dcd" % epsilon)

            # Ptraj files
            ptraj_conf = File("ptraj_%s.conf" % epsilon)
            ptraj_dcd = File("ptraj_%s.dcd" % epsilon)

            # Sassena incoherent files
            incoherent_conf = File("sassenaInc_%s.xml" % epsilon)
            fqt_incoherent = File("fqt_inc_%s.hd5" % epsilon)

            # Sassena coherent files
            coherent_conf = File("sassenaCoh_%s.xml" % epsilon)
            fqt_coherent = File("fqt_coh_%s.hd5" % epsilon)

            # Generate psf and configuration files for this epsilon pipeline
            self.generate_prm(epsilon)
            self.generate_eq_conf(epsilon, parameters)
            self.generate_prod_conf(epsilon, parameters)
            self.generate_ptraj_conf(epsilon)
            self.generate_incoherent_conf(epsilon)
            self.generate_coherent_conf(epsilon)

            # Equilibrate job
            eqjob = Job("namd", node_label="namd_eq_%s" % epsilon)
            eqjob.addArguments(eq_conf)
            eqjob.uses(eq_conf, link=Link.INPUT)
            eqjob.uses(structure, link=Link.INPUT)
            eqjob.uses(coordinates, link=Link.INPUT)
            eqjob.uses(parameters, link=Link.INPUT)
            eqjob.uses(fixed_pdb, link=Link.INPUT)
            eqjob.uses(extended_system, link=Link.INPUT)
            eqjob.uses(bin_coordinates, link=Link.INPUT)
            eqjob.uses(bin_velocities, link=Link.INPUT)
            eqjob.uses(eq_coord, link=Link.OUTPUT, transfer=False)
            eqjob.uses(eq_xsc, link=Link.OUTPUT, transfer=False)
            eqjob.uses(eq_vel, link=Link.OUTPUT, transfer=False)
            eqjob.profile("globus", "jobtype", "mpi")
            eqjob.profile("globus", "maxwalltime", "360")
            eqjob.profile("globus", "count", "240")
            dax.addJob(eqjob)

            # Production job
            prodjob = Job("namd", node_label="namd_prod_%s" % epsilon)
            prodjob.addArguments(prod_conf)
            prodjob.uses(prod_conf, link=Link.INPUT)
            prodjob.uses(structure, link=Link.INPUT)
            prodjob.uses(coordinates, link=Link.INPUT)
            prodjob.uses(parameters, link=Link.INPUT)
            prodjob.uses(fixed_pdb, link=Link.INPUT)
            prodjob.uses(eq_coord, link=Link.INPUT)
            prodjob.uses(eq_xsc, link=Link.INPUT)
            prodjob.uses(eq_vel, link=Link.INPUT)
            prodjob.uses(prod_dcd, link=Link.OUTPUT, transfer=True)
            prodjob.profile("globus", "jobtype", "mpi")
            prodjob.profile("globus", "maxwalltime", "5760")
            prodjob.profile("globus", "count", "240")
            dax.addJob(prodjob)
            dax.depends(prodjob, eqjob)

            # ptraj job
            ptrajjob = Job(namespace="amber", name="ptraj", node_label="amber_ptraj_%s" % epsilon)
            ptrajjob.addArguments(coordinates)
            ptrajjob.setStdin(ptraj_conf)
            ptrajjob.uses(coordinates, link=Link.INPUT)
            ptrajjob.uses(ptraj_conf, link=Link.INPUT)
            ptrajjob.uses(prod_dcd, link=Link.INPUT)
            ptrajjob.uses(ptraj_dcd, link=Link.OUTPUT, transfer=True)
            ptrajjob.profile("globus", "jobtype", "single")
            ptrajjob.profile("globus", "maxwalltime", "60")
            ptrajjob.profile("globus", "count", "1")
            dax.addJob(ptrajjob)
            dax.depends(ptrajjob, prodjob)

            # sassena incoherent job
            incojob = Job("sassena", node_label="sassena_inc_%s" % epsilon)
            incojob.addArguments("--config", incoherent_conf)
            incojob.uses(incoherent_conf, link=Link.INPUT)
            incojob.uses(ptraj_dcd, link=Link.INPUT)
            incojob.uses(incoherent_db, link=Link.INPUT)
            incojob.uses(sassena_pdb, link=Link.INPUT)
            incojob.uses(fqt_incoherent, link=Link.OUTPUT, transfer=True)
            incojob.profile("globus", "jobtype", "mpi")
            incojob.profile("globus", "maxwalltime", "360")
            incojob.profile("globus", "count", "120")
            dax.addJob(incojob)
            dax.depends(incojob, ptrajjob)
            dax.depends(incojob, untarjob)

            # sassena coherent job
#            cojob = Job("sassena", node_label="sassena_coh_%s" % epsilon)
#            cojob.addArguments("--config", coherent_conf)
#            cojob.uses(coherent_conf, link=Link.INPUT)
#            cojob.uses(ptraj_dcd, link=Link.INPUT)
#            cojob.uses(coherent_db, link=Link.INPUT)
#            cojob.uses(sassena_pdb, link=Link.INPUT)
#            cojob.uses(fqt_coherent, link=Link.OUTPUT, transfer=True)
#            cojob.profile("globus", "jobtype", "mpi")
#            cojob.profile("globus", "maxwalltime", "360")
#            cojob.profile("globus", "count", "400")
#            dax.addJob(cojob)
#            dax.depends(cojob, prodjob)
#            dax.depends(cojob, untarjob)

        # Write the DAX file
        dax.writeXMLFile(self.daxfile)

        # Finally, generate the replica catalog
        self.generate_replica_catalog()

def main():
    if len(sys.argv) != 3:
        raise Exception("Usage: %s CONFIGFILE OUTDIR" % sys.argv[0])

    configfile = sys.argv[1]
    outdir = sys.argv[2]
    root = Tk()
    root.withdraw()
    root.title("Pegasus input")
    d = MyDialog(root)
    
    epsilons = d.result[0]
    temperature = float(d.result[1])
    structure = d.result[2]
    sassena_pdb = d.result[3]
    equilibrate_steps = int(d.result[4])
    production_steps = int(d.result[5])
    coordinates = d.result[6]
    fixed_pdb = d.result[7]
    extended_system = d.result[8]
    bin_coordinates = d.result[9]
    bin_velocities  = d.result[10]
    sassena_db = d.result[11]
    # Write or over-write anvred3.inp file
    user_input = open( configfile, 'w' )
    user_input.write( d.header + '\n' )
    for i in range( len( d.result ) ):
        user_input.write( d.label_text[i] + d.label_name[i] + '=' + d.result[i] + '\n' )
    user_input.close()




    if not os.path.isfile(configfile):
        raise Exception("No such file: %s" % configfile)

    if os.path.isdir(outdir):
        raise Exception("Directory exists: %s" % outdir)

    # Create the output directory
    outdir = os.path.abspath(outdir)
    os.makedirs(outdir)

    # Read the config file
    config = ConfigParser()
    config.read(configfile)

    # Generate the workflow in outdir based on the config file
    workflow = RefinementWorkflow(outdir, config)
    workflow.generate_workflow()
    return_code = subprocess.call("myproxy-logon -s nerscca.nersc.gov:7512 -t 720 -T -l vlynch ", shell=True)
    proc = subprocess.Popen(['./plan.sh', outdir], stdout=subprocess.PIPE) 
    for line in proc.stdout:
        if "pegasus-run" in line:
            return_code = subprocess.call(line, shell=True)

if __name__ == '__main__':
    main()

