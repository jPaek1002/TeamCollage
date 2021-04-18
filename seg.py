#!/usr/bin/env python
# --*-- coding: utf-8 --*--
import os
import sys
import argparse
import numpy as np
import cv2
# import matplotlib.pyplot as plt
from os import listdir
# from os.path import isfile, join

import torch
from torchvision.models.segmentation import deeplabv3_resnet101
from torchvision import transforms

from FBA_Matting.demo import np_to_torch, pred, scale_input
from FBA_Matting.dataloader import read_image, read_trimap
from FBA_Matting.networks.models import build_model


deeplab_preprocess = transforms.Compose([
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])
class Args:
    encoder = 'resnet50_GN_WS'
    decoder = 'fba_decoder'
    weights = 'FBA.pth'


def segment_img(img_name, output_name):
    device = torch.device("cpu")
    deeplab = make_deeplab(device)
    f_name = img_name
    img_orig = cv2.imread(f_name, 1)

    # plt.imshow(img_orig[:, :, ::-1])
    # plt.show()

    k = min(1.0, 1024/max(img_orig.shape[0], img_orig.shape[1]))
    img = cv2.resize(img_orig, None, fx=k, fy=k, interpolation=cv2.INTER_LANCZOS4)

    mask = apply_deeplab(deeplab, img, device)

    # plt.imshow(mask, cmap="gray")
    # plt.show()

    args=Args()
    model = build_model(args)

    trimap = np.zeros((mask.shape[0], mask.shape[1], 2))
    trimap[:, :, 1] = mask > 0
    trimap[:, :, 0] = mask == 0
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(25,25))

    trimap[:, :, 0] = cv2.erode(trimap[:, :, 0], kernel)
    trimap[:, :, 1] = cv2.erode(trimap[:, :, 1], kernel)

    trimap_im =  trimap[:,:,1] + (1-np.sum(trimap,-1))/2
    # plt.imshow(trimap_im, cmap='gray', vmin=0, vmax=1)
    # plt.show()

    fg, bg, alpha = pred((img/255.0)[:, :, ::-1], trimap, model)

    img_ = img_orig.astype(np.float32)/255
    alpha_ = cv2.resize(alpha, (img_.shape[1], img_.shape[0]), cv2.INTER_LANCZOS4)
    fg_alpha = np.concatenate([img_, alpha_[:, :, np.newaxis]], axis=2)

    final_img = (fg_alpha*255).astype(np.uint8)
    # axis 0 is the row(y) and axis(x) 1 is the column
    y,x = final_img[:,:,3].nonzero() # get the nonzero alpha coordinates
    minx = np.min(x)
    miny = np.min(y)
    maxx = np.max(x)
    maxy = np.max(y)

    cropImg = final_img[miny:maxy, minx:maxx]
    cv2.imwrite(output_name + ".png", cropImg)


def make_deeplab(device):
    deeplab = deeplabv3_resnet101(pretrained=True).to(device)
    deeplab.eval()
    return deeplab


def apply_deeplab(deeplab, img, device):
    input_tensor = deeplab_preprocess(img)
    input_batch = input_tensor.unsqueeze(0)
    with torch.no_grad():
        output = deeplab(input_batch.to(device))['out'][0]
    output_predictions = output.argmax(0).cpu().numpy()
    return (output_predictions == 15)


def main(args):

    # Get input image file names.
    img_fnames = []
    if os.path.isfile(args.in_path):
        img_fnames = [args.in_path]
    elif os.path.isdir(args.in_path):
        fnames = [os.path.join(os.path.abspath(args.in_path),x) for x in listdir(args.in_path)]
        for fname in fnames:
            file_ext = os.path.splitext(fname)[1][1:]
            if file_ext in ["jpg", "png", "tif"]:
                img_fnames.append(fname)
    else:
        sys.exit()
    # print(img_fnames)

    if not os.path.isdir(args.out_folder):
        os.makedirs(args.out_folder)

    for img_fname in img_fnames:
        fname = os.path.splitext(os.path.basename(img_fname))
        out_fname = os.path.join(args.out_folder, "seg.{}".format(fname))
        segment_img(img_fname, out_fname)


def parse_arguments(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--in_path", required=True, help="Input path")
    parser.add_argument("--out_folder", default=".", help="Output folder")

    args = parser.parse_args(argv)

    return args


if __name__ == "__main__":
    if len(sys.argv) == 1:
        sys.argv.extend(["--help"])
    main(parse_arguments(sys.argv[1:]))
