import json
import os
import numpy as np
from PIL import Image
from PIL import ImageOps
from skimage import color as skcolor
from skimage import io as skio
import matplotlib.pyplot as plt
from scipy.misc import imresize
from mpl_toolkits.mplot3d import Axes3D
from matplotlib.collections import LineCollection


#define variables outside (default vals)
#setter functions to update these values
#allow for offset of valves (distance specified in config)
#how to specify which valve you're using (based on black/white color)
x = 0
y = 0
z = 0
heatbed_temp = 37
usecs = 100
unitsize = 1
# offset = 10
#r = extruder 0, g, b

# color map for visualizing print
COLOR_MAP = {"valve 0": 'r', "valve 1": 'g', "valve 3": 'b'}

class GCommand(object):
    """Class representing a single action of the a microvalve"""

    def __init__(self, x, y, z, material, usecs=100):
        """
        Init

        x, x location in gcode coords
        y, y location in gcode coords
        z, z location in gcode coords
        material, material indicator
        usecs, delay after movement
        """
        self.x = x
        self.y = y
        self.z = z
        self.material = material
        self.usecs = usecs
    
    def __str__(self):
        """Returns gcode representation of command"""
        if self.material == "valve 0":
            return "T0; G0 E10; G1 X{} Y{} ;material {}\nM400 ;wait for position\nG4 P100\nM430 S{} ;send pulse"\
            .format(self.x, self.y, self.material, self.usecs)
        elif self.material == "valve 1":
            return "T1; G0 E20; G1 X{} Y{} ;material {}\nM400 ;wait for position\nG4 P100\nM430 S{} ;send pulse"\
            .format(self.x, self.y, self.material, self.usecs)
        elif self.material == "valve 2":
            return "T2; G0 E30; G1 X{} Y{} ;material {}\nM400 ;wait for position\nG4 P100\nM430 S{} ;send pulse"\
            .format(self.x, self.y, self.material, self.usecs)
        else:
            return ""


def write_json(filename):
    """
    Write a json config

    filename, path to write to
    """
    data = {"x":0, "y":0, "z":0, "heatbed_temp":37, "usecs": 100, "unitsize":1, "folder":"test_layers"}
    with open(filename, "w") as fp:
        json.dump(data, fp)

def load_json(filename):
    """
    Load a json config

    filename, path to load

    return data, dictionary object with config
    """
    with open(filename, "r") as fp:
        data = json.load(fp)
    x = data["x"]
    y = data["y"]
    z = data["z"]
    heatbed_temp = data["heatbed_temp"]
    usecs = data["usecs"]
    unitsize = data["unitsize"]
    # offset = data["offset"]
    return data

def load_raw_images(folder_path, check_dims=True):
    """
    Load images in raw form

    folder_path, path to folder with images
    check_dims, boolean to assert that all images have the same size

    returns images, list of ndarrays of dimension height x width x 3 (color channels)
    """
    images = []

    for image_path in os.listdir(folder_path):
        try:
            image = skio.imread(os.path.join(folder_path, image_path))
            images.append(image)
        except Exception:
            print("{} cannot be opened".format(image_path))

    if check_dims:
        assert all((image.shape == images[0].shape for image in images)), "images do not have equal dimensions"
    
    return images

def convert_to_binary(images):
    """
    Flatten images to black and white. This function is useful for testing
    but should be deprecated.

    images, list of ndarrays of dimension height x width x 3 (color channels)

    return binarys, list of ndarrays of dimension height x width (elements are 0 or 1)
    """
    # grays = [skcolor.rgb2gray(image) for image in images]
    # binarys = []

#     for image in grays:
#         binary = image.copy().astype(np.uint8)
#         binary[image <= 0.5] = 1
#         binary[image > 0.5] = 0
#         binarys.append(binary)

#     return binarys

def resize_images(images, size):
    """
    Resize images

    images, list of ndarrays
    size, desired size

    return list of resized images
    """
    return [imresize(image, size) for image in images]

def convert_to_gcode(binary_layers, usecs=600, grid_unit=0.5, z_unit=1.0, start_x=40, start_y=50, flip_flop=True):
    """
    Convert a list of binary images to gcommands. Iterates over each pixel
    and forms a GCommand object

    binary_layers, list of ndarrays of dimension height x width (elements are 0 or 1)
    usecs, delay for GCommand
    grid_unit, conversion of pixel to g-code dimensions in x and y
    z_unit, conversion of pixel to g-code dimensions in z
    start_x, start x location in g-code
    start_y, start y location in g-code
    flip_flop, boolean flip scans of left and right to minimize tracking
    """

    gcommands = []
    num_layers = len(binary_layers)
    for grid_z in range(num_layers):
        for grid_y in range(binary_layers[grid_z].shape[0]):
            if grid_y % 2 == 0 and flip_flop:
                x_iterator = reversed(range(binary_layers[grid_z].shape[1]))
            else:
                x_iterator = range(binary_layers[grid_z].shape[1])
            for grid_x in x_iterator:
                pixel = binary_layers[grid_z][grid_y, grid_x]
                material = convert_to_material(pixel)

                gcommand = GCommand(grid_x * grid_unit + start_x, \
                                    grid_y * grid_unit + start_y, \
                                    grid_z * z_unit, \
                                    material, \
                                    # binary_layers[grid_z][grid_y, grid_x], \
                                    usecs)
                gcommands.append(gcommand)

    return gcommands

def convert_to_material(pixel):
    red = pixel[0]
    green = pixel[1]
    blue = pixel[2]
    if (red, green, blue) == (255, 255, 255):
        return None
    if red == 255:
        return "valve 0"
    if green == 255:
        return "valve 1"
    if blue == 255:
        return "valve 3"
    else:
        print("Unrecognized color: (r: {}, g: {}, b: {})".format(red, green, blue))

def write_gcode(gcommands, gcode_path, heatbed_temp=37):
    """
    Convert list of gcommands into .gcode file. Also prepend info

    gcommands, list of GCommand objects
    gcode_path, path to write output
    heatbed_temp, start temp
    """
    if (heatbed_temp <= 200):
        # start_gcode = 'M42 P4 S250\n' + 'G21 ;metric values\nG90 ;absolute positioning\n'+\
        # 'G28 X0 Y0 ;move X/Y to min endstops\n'+\
        # 'M190 S' + str(min(heatbed_temp, 200)) + ' ; set heatbed temp\nM117 Printing...'
        # end_gcode= 'M42 P4 S255\n' + 'M84 ;steppers off\nM140 S0 ; turn off heatbed\n;done printing'
        start_gcode = 'M42 P4 S250'

        end_gcode= 'M42 P4 S255'
        with open(gcode_path, 'w') as gcode_file:
            gcode_file.write(start_gcode)
            gcode_file.write('\n')
            
            for gcommand in gcommands:
                gcode_file.write(str(gcommand))
                gcode_file.write('\n')
            
            gcode_file.write(end_gcode)
            gcode_file.write('\n')
    else:
        print("{} > max temp 200".format(heatbed_temp))

def graph(gcommands, color_map=COLOR_MAP):
    """
    Graph gcommands in 3d

    gcommands, list of GCommand objects
    """
    fig = plt.figure(figsize=(10,10))
    ax = fig.add_subplot(111, projection='3d')
    materials = set((gcommand.material for gcommand in gcommands))
    split_on_materials = dict(((material, []) for material in materials))

    for gcommand in gcommands:
        split_on_materials[gcommand.material].append(gcommand)

    if color_map is None:
        from matplotlib import colors as cnames
        from itertools import cycle
        color_names = [name for name in cnames.cnames]
        color_names.sort()
        colors = cycle(color_names)
        color_map = dict(zip(materials, colors))

    for material, split in \
        [(material, split) for (material, split) \
        in split_on_materials.items() if material is not None]:
        xs = [gcommand.x for gcommand in split]
        ys = [gcommand.y for gcommand in split]
        zs = [gcommand.z for gcommand in split]
        ax.scatter(xs, ys, zs, c=color_map[material], label=material)

    xmin = min((gcommand.x for gcommand in gcommands))
    xmax = max((gcommand.x for gcommand in gcommands))
    ymin = min((gcommand.y for gcommand in gcommands))
    ymax = max((gcommand.y for gcommand in gcommands))
    zmin = min((gcommand.z for gcommand in gcommands))
    zmax = max((gcommand.z for gcommand in gcommands))

    ax.set_xlabel('x')
    ax.set_ylabel('y')
    ax.set_zlabel('z')
    ax.set_xlim3d(xmin, xmax)
    ax.set_ylim3d(ymin, ymax)
    ax.set_zlim3d(zmin, zmax)
    # ax.invert_xaxis()

    plt.legend()
    plt.show()

def flip_images(images):
    """
    Flip images vertically without overwriting

    images, list of height x width x 3 (color channels)

    return flipped_images, images where each image is flipped vertically
    """
    new_images = []

    for image in images:
        new_image = np.copy(image)
        for y in range(image.shape[0]):
            flipped_y = image.shape[0] - y - 1
            for x in range(image.shape[1]):
                pixel = image[y, x]
                new_image[flipped_y, x] = pixel
        new_images.append(new_image)

    return(new_images)


def main():
    """
    Cal printing demo
    """
    data = load_json("config.json")
    raws = load_raw_images(data["folder"])

    flipped_images = flip_images(raws)
    
    # size = (100, 100)
    # resizes = resize_images(raws, size)

    gcommands = convert_to_gcode(flipped_images, usecs= data["usecs"], grid_unit=data["unitsize"], start_x=data["x"], start_y=data["y"])
    # gcommands = convert_to_gcode(binarys, usecs= data["usecs"], grid_unit=data["unitsize"], start_x=data["x"], start_y=data["y"])
    
    write_gcode(gcommands, 'test.gcode', data["heatbed_temp"])
    graph(gcommands)

if __name__ == '__main__':
    main()